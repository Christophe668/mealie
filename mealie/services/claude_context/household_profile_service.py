from collections.abc import Callable
from typing import Literal, get_args
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from mealie.core.exceptions import NoEntryFound
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.household import household_profile
from mealie.schema.household.household_profile import (
    HouseholdProfileOut,
    MealPreferencesOut,
    MealPreferencesUpdate,
    MemberProfileCreate,
    MemberProfileOut,
    MemberProfileUpdate,
)
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService

ProfileListField = Literal["allergies", "exclusions", "dislikes", "likes"]
PROFILE_LIST_FIELDS: tuple[str, ...] = get_args(ProfileListField)


class ProfileConflict(ValueError):
    """A second profile with the same name (case-insensitive) or for the same user in this household."""


USER_LINK_CONSTRAINT = "household_member_profiles_household_id_user_id_key"


def _is_user_link_violation(error: IntegrityError) -> bool:
    """Whether `error` is the `(household_id, user_id)` unique constraint: PostgreSQL names the constraint, SQLite
    lists its columns ("UNIQUE constraint failed: household_member_profiles.household_id, …user_id")."""
    message = str(error.orig)
    if USER_LINK_CONSTRAINT in message:
        return True
    return (
        "UNIQUE constraint failed" in message
        and "household_member_profiles.household_id" in message
        and "household_member_profiles.user_id" in message
    )


class HouseholdProfileService(BaseService):
    """Member profiles and meal habits of the user's household (spec § 2, § 4).

    Rules on top of the write schemas: a name is unique per household, case-insensitively; a linked `user_id` must
    be a user of this household, and at most one profile links to it. Everything is checked before the write.

    Every write method makes a single repository call, which commits on its own, so a refused request writes
    nothing. The database's unique constraint on `(household_id, user_id)` backs the user rule against concurrent
    requests and surfaces as `ProfileConflict` too; the name rule is a service check only (spec § 2), so two
    concurrent creates of the same name can both succeed.
    """

    def __init__(self, repos: AllRepositories, user: PrivateUser):
        # member scope comes from `repos`, the user-link rule from `user`: they must name the same household, so a
        # group-scoped (or another household's) repos can never reach other households' profiles
        scope = repos.member_profiles
        if str(scope.household_id) != str(user.household_id) or str(scope.group_id) != str(user.group_id):
            raise ValueError("HouseholdProfileService needs repositories scoped to the user's household.")
        self.repos = repos
        self.user = user
        self.members = repos.member_profiles
        self.preferences = repos.meal_preferences
        super().__init__()

    @staticmethod
    def normalise_list(values: list[str]) -> list[str]:
        """The write schemas' list rule: trim, drop empty, de-duplicate case-insensitively (first spelling wins).

        Raises `ValueError` when an entry is longer than 60 characters or more than 30 distinct entries remain.
        """
        return household_profile.normalise_list(values)

    # ------------------------------------------------------------------ reads

    def get(self) -> HouseholdProfileOut:
        """Members in display order and the household's preferences (`None` before the first write).

        Never looks linked users up: on SQLite a deleted user leaves its id behind, which must not break the read.
        """
        return HouseholdProfileOut(members=self.members.ordered(), preferences=self.preferences.get_for_household())

    def _get_or_raise(self, member_id: UUID) -> MemberProfileOut:
        # household-scoped: another household's profile is not found
        member = self.members.get_one(member_id)
        if member is None:
            raise NoEntryFound("Member profile not found.")
        return member

    def _resolve(self, member_ref: str) -> MemberProfileOut:
        """A profile by id (UUID string) or by name, case-insensitively."""
        try:
            member_id = UUID(member_ref.strip())
        except ValueError:
            member = None
        else:
            member = self.members.get_one(member_id)
        if member is not None:
            return member
        matches = self.members.all_by_name_casefold(member_ref)
        if not matches:
            raise NoEntryFound("Member profile not found.")
        if len(matches) > 1:
            # never pick one: allergies are hard constraints
            raise ProfileConflict(f"Several members are named {member_ref.strip()!r}; use the member id instead.")
        return matches[0]

    # ------------------------------------------------------------------ rules

    def _check_name(self, name: str, member_id: UUID | None = None) -> None:
        clash = self.members.by_name_casefold(name)
        if clash is not None and clash.id != member_id:
            raise ProfileConflict(f"A member named {clash.name!r} already exists.")

    def _check_user(self, user_id: UUID, member_id: UUID | None = None) -> None:
        """`user_id` must be a user of this household that no other profile links to.

        `repos.users` is group-scoped, so the household is compared here; a user elsewhere is "not found".
        """
        linked = self.repos.users.get_one(user_id)
        if linked is None or str(linked.household_id) != str(self.user.household_id):
            raise NoEntryFound("User not found.")
        existing = self.members.by_user(user_id)
        if existing is not None and existing.id != member_id:
            raise ProfileConflict(f"{existing.name!r} is already linked to this user.")

    def _write(self, write: Callable[[], MemberProfileOut]) -> MemberProfileOut:
        """Run one member write, turning any integrity error into a conflict.

        Only a lost race on the `(household_id, user_id)` constraint gets the user-link message; anything else (on
        PostgreSQL, a linked user deleted between the check and the write breaks the foreign key) stays neutral.
        """
        try:
            return write()
        except IntegrityError as e:
            self.repos.session.rollback()
            if _is_user_link_violation(e):
                raise ProfileConflict("This user is already linked to another member.") from e
            raise ProfileConflict("Conflicting profile data; reload and try again.") from e

    # ------------------------------------------------------------------ member writes

    def create_member(self, data: MemberProfileCreate) -> MemberProfileOut:
        """Raises `ProfileConflict` for a duplicate name or user, `NoEntryFound` for a user outside the household."""
        self._check_name(data.name)
        if data.user_id is not None:
            self._check_user(data.user_id)
        return self._write(lambda: self.members.create(data))

    def update_member(self, member_id: UUID, data: MemberProfileUpdate) -> MemberProfileOut:
        """A partial update: only the fields sent change.

        Built from `exclude_unset`, never a full dump: the model stores a `None` list as `[]`, so unsent lists would
        be wiped. Only a changed `user_id` is checked, so a stale link left by a deleted user stays editable.
        """
        existing = self._get_or_raise(member_id)
        values = data.model_dump(exclude_unset=True)
        if "name" in values:
            self._check_name(values["name"], existing.id)
        user_id = values.get("user_id")
        if user_id is not None and user_id != existing.user_id:
            self._check_user(user_id, existing.id)
        if not values:
            return existing
        return self._write(lambda: self.members.update(existing.id, values))

    def delete_member(self, member_id: UUID) -> MemberProfileOut:
        existing = self._get_or_raise(member_id)
        return self.members.delete(existing.id)

    def add_to_member(self, member_ref: str, field: ProfileListField, values: list[str]) -> MemberProfileOut:
        """Append `values` to one of a member's lists without replacing it ("Sam doesn't like mushrooms").

        `member_ref` is the profile id or its name (case-insensitive); a name shared by several profiles raises
        `ProfileConflict` rather than picking one. The combined list goes through the write
        schemas' rule, so duplicates collapse onto the existing spelling, and an entry over 60 characters or a
        list over 30 entries raises `ValueError` before anything is written.
        """
        if field not in PROFILE_LIST_FIELDS:
            raise ValueError(f"field must be one of {', '.join(PROFILE_LIST_FIELDS)}")
        member = self._resolve(member_ref)
        combined = self.normalise_list([*getattr(member, field), *values])
        return self.members.update(member.id, {field: combined})

    # ------------------------------------------------------------------ preferences

    def update_preferences(self, data: MealPreferencesUpdate) -> MealPreferencesOut:
        """Create the household's preferences row on first write, otherwise update only the fields sent."""
        values = data.model_dump(exclude_unset=True)
        existing = self.preferences.get_for_household()
        if existing is None:
            try:
                return self.preferences.create(values)
            except IntegrityError:
                # a concurrent request created the row first (unique household_id): update it instead
                self.repos.session.rollback()
                existing = self.preferences.get_for_household()
                if existing is None:
                    raise
        if not values:
            return existing
        return self.preferences.update(existing.id, values)
