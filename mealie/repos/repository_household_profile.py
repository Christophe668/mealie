from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, select

from mealie.db.models.household.household_profile import HouseholdMealPreferences, HouseholdMemberProfile
from mealie.schema.household.household_profile import MealPreferencesOut, MemberProfileOut

from .repository_generic import HouseholdRepositoryGeneric


def _with_scope(repo: HouseholdRepositoryGeneric, data: BaseModel | dict) -> dict[str, Any]:
    """Return `data` as a dict carrying `repo`'s scope.

    A scoped repository always writes its own `group_id`/`household_id`, whatever the caller passed;
    only an unscoped repository honours the ids in `data`.
    """
    values = dict(data) if isinstance(data, dict) else data.model_dump()
    if repo.group_id is not None:
        values["group_id"] = repo.group_id
    if repo.household_id is not None:
        values["household_id"] = repo.household_id
    return values


class RepositoryMemberProfiles(HouseholdRepositoryGeneric[MemberProfileOut, HouseholdMemberProfile]):
    def create(self, data: MemberProfileOut | BaseModel | dict) -> MemberProfileOut:
        return super().create(_with_scope(self, data))

    def create_many(self, data: Iterable[MemberProfileOut | BaseModel | dict]) -> list[MemberProfileOut]:
        return super().create_many([_with_scope(self, item) for item in data])

    def _scoped_select(self) -> Select[tuple[HouseholdMemberProfile]]:
        stmt = select(HouseholdMemberProfile)
        if self.group_id:
            stmt = stmt.filter(HouseholdMemberProfile.group_id == self.group_id)
        if self.household_id:
            stmt = stmt.filter(HouseholdMemberProfile.household_id == self.household_id)
        return stmt

    def _all(self, stmt: Select[tuple[HouseholdMemberProfile]]) -> list[MemberProfileOut]:
        return [self.schema.model_validate(row) for row in self.session.execute(stmt).scalars().all()]

    def ordered(self) -> list[MemberProfileOut]:
        """Profiles in display order: `position` ascending, then name case-folded, then `id` descending.

        The name is folded in Python because SQLite's `lower()` only folds ASCII ("Émile" would sort after "zoe").
        """
        stmt = self._scoped_select().order_by(HouseholdMemberProfile.position.asc(), HouseholdMemberProfile.id.desc())
        rows = self._all(stmt)
        # `sorted` is stable, so equal (position, folded name) keep the query's `id` descending order.
        return sorted(rows, key=lambda row: (row.position, row.name.casefold()))

    def by_user(self, user_id: UUID) -> MemberProfileOut | None:
        """The household's profile linked to `user_id`, if any (at most one, enforced by a unique constraint)."""
        row = self.session.execute(
            self._scoped_select().filter(HouseholdMemberProfile.user_id == user_id)
        ).scalar_one_or_none()
        return None if row is None else self.schema.model_validate(row)

    def by_name_casefold(self, name: str) -> MemberProfileOut | None:
        """The household's profile whose trimmed name equals `name`, case-folded.

        Compared in Python because SQLite's `lower()` only folds ASCII ("Crème" != "CRÈME").
        """
        target = name.strip().casefold()
        stmt = self._scoped_select().order_by(HouseholdMemberProfile.id.desc())
        return next((row for row in self._all(stmt) if row.name.strip().casefold() == target), None)


class RepositoryMealPreferences(HouseholdRepositoryGeneric[MealPreferencesOut, HouseholdMealPreferences]):
    def create(self, data: MealPreferencesOut | BaseModel | dict) -> MealPreferencesOut:
        return super().create(_with_scope(self, data))

    def create_many(self, data: Iterable[MealPreferencesOut | BaseModel | dict]) -> list[MealPreferencesOut]:
        return super().create_many([_with_scope(self, item) for item in data])

    def get_for_household(self) -> MealPreferencesOut | None:
        """This household's preferences row, or `None` before the first write.

        Needs a household-scoped repository: an unscoped one has no single household to answer for.
        """
        if self.household_id is None:
            raise ValueError("get_for_household needs a household-scoped repository")
        stmt = select(HouseholdMealPreferences).filter(HouseholdMealPreferences.household_id == self.household_id)
        if self.group_id:
            stmt = stmt.filter(HouseholdMealPreferences.group_id == self.group_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        return None if row is None else self.schema.model_validate(row)
