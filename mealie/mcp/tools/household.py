from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ValidationError

from mealie.core.exceptions import NoEntryFound
from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext
from mealie.mcp.errors import McpToolError, not_found
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.schema.household.household_profile import (
    MealPreferencesOut,
    MealPreferencesUpdate,
    MemberProfileCreate,
    MemberProfileOut,
    MemberProfileUpdate,
    name_key,
    normalise_list,
)
from mealie.services.claude_context.household_profile_service import (
    PROFILE_LIST_FIELDS,
    HouseholdProfileService,
    ProfileConflict,
    ProfileListField,
)

DEFAULT_LOCALE = "en-US"

# The keys spec § 4 advertises; `position` (display order) stays a UI concern.
_MEMBER_FIELDS = frozenset(
    {"name", "user_id", "is_child", "diet", "allergies", "exclusions", "dislikes", "likes", "notes"}
)
_MEMBER_KEYS = _MEMBER_FIELDS | {"id"}
_HOUSEHOLD_KEYS = frozenset(MealPreferencesUpdate.model_fields)
_ADD_TO_KEYS = frozenset({"member", "field", "values"})


# ---------------------------------------------------------------------- reads


def _member_dict(member: MemberProfileOut, current_user_id: UUID) -> dict[str, Any]:
    return {
        "id": str(member.id),
        "name": member.name,
        "is_child": member.is_child,
        "diet": member.diet.value,
        "allergies": list(member.allergies),
        "exclusions": list(member.exclusions),
        "dislikes": list(member.dislikes),
        "likes": list(member.likes),
        "notes": member.notes,
        "is_current_user": member.user_id is not None and str(member.user_id) == str(current_user_id),
    }


def _household_dict(preferences: MealPreferencesOut | None) -> dict[str, Any] | None:
    if preferences is None:
        return None
    return {
        "default_servings": preferences.default_servings,
        "quick_weekdays": list(preferences.quick_weekdays),
        "weeknight_max_minutes": preferences.weeknight_max_minutes,
        "weekend_max_minutes": preferences.weekend_max_minutes,
        "favourite_cuisines": list(preferences.favourite_cuisines),
        "notes": preferences.notes,
    }


def _preferences(ctx: McpContext) -> dict[str, Any]:
    """Spec § 4: `{members: [...], household: {...} | null}`, members in display order."""
    profile = HouseholdProfileService(ctx.repos, ctx.user).get()
    return {
        "members": [_member_dict(m, ctx.user.id) for m in profile.members],
        "household": _household_dict(profile.preferences),
    }


def get_household_context_impl(ctx: McpContext) -> dict[str, Any]:
    user = ctx.user
    group = ctx.repos.groups.get_one(user.group_id)
    household = ctx.repos.households.get_one(user.household_id)
    members = ctx.repos.users.multi_query({"household_id": user.household_id})

    return {
        "group": {
            "id": str(user.group_id),
            "name": group.name if group else user.group,
            "slug": group.slug if group else user.group_slug,
        },
        "household": {"id": str(user.household_id), "name": household.name if household else user.household},
        "members": [
            {"id": str(m.id), "full_name": m.full_name, "username": m.username}
            for m in sorted(members, key=lambda m: (m.full_name or "").lower())
        ],
        "user": {"id": str(user.id), "full_name": user.full_name},
        "first_day_of_week": household.preferences.first_day_of_week if household and household.preferences else 0,
        # Mealie keeps the UI language in the browser only; there is no server-side locale yet.
        "locale": DEFAULT_LOCALE,
        "today": datetime.now().astimezone().date().isoformat(),
        "scopes_granted": sorted(ctx.access.scopes),
        "preferences": _preferences(ctx),
    }


# ---------------------------------------------------------------------- validation


@dataclass
class _Draft:
    """One member as it will be once the batch is applied; the batch is replayed on these before any write."""

    name: str
    user_id: UUID | None
    lists: dict[str, list[str]] = field(default_factory=dict)
    id: UUID | None = None  # None for a member created in this call


def _check_keys(entry: Any, allowed: frozenset[str], where: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise McpToolError(f"{where}: expected an object")
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise McpToolError(f"{where}: unknown key(s) {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}")
    return dict(entry)


def _parse_member_id(value: Any) -> UUID:
    try:
        return UUID(str(value).strip())
    except ValueError as e:
        raise not_found("member", str(value)) from e


def _validate[M: BaseModel](model: type[M], fields: dict[str, Any], where: str) -> M:
    try:
        return model.model_validate(fields)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(str(p) for p in err['loc']) or 'entry'}: {err['msg']}" for err in e.errors())
        raise McpToolError(f"{where}: {problems}") from e


def _key(name: str) -> str:
    return name_key(name)


class _Batch:
    """Replays the whole call on in-memory drafts, in the order it will be written (removes, updates, creates,
    add_to), applying the service's rules at each step. The service writers commit one by one, so this is what
    guarantees that a refused call writes nothing."""

    def __init__(self, ctx: McpContext, existing: list[MemberProfileOut]):
        self.ctx = ctx
        self.existing = {m.id: m for m in existing}
        self.drafts: list[_Draft] = [
            _Draft(m.name, m.user_id, {f: list(getattr(m, f)) for f in PROFILE_LIST_FIELDS}, m.id) for m in existing
        ]

    def _draft(self, member_id: UUID) -> _Draft | None:
        return next((d for d in self.drafts if d.id == member_id), None)

    def remove(self, member_id: UUID) -> None:
        self.drafts = [d for d in self.drafts if d.id != member_id]

    def _check_name(self, name: str, draft: _Draft | None, where: str) -> None:
        clash = next((d for d in self.drafts if d is not draft and _key(d.name) == _key(name)), None)
        if clash is not None:
            raise McpToolError(f"{where}: a member named {clash.name!r} already exists")

    def _check_user(self, user_id: UUID, draft: _Draft | None, where: str) -> None:
        linked = self.ctx.repos.users.get_one(user_id)  # group-scoped: compare the household here
        if linked is None or str(linked.household_id) != str(self.ctx.user.household_id):
            raise McpToolError(f"{where}: user not found: {user_id}")
        other = next((d for d in self.drafts if d is not draft and d.user_id == user_id), None)
        if other is not None:
            raise McpToolError(f"{where}: {other.name!r} is already linked to this user")

    def update(self, member_id: UUID, data: MemberProfileUpdate, where: str) -> None:
        draft = self._draft(member_id)
        assert draft is not None  # checked by the caller
        values = data.model_dump(exclude_unset=True)
        if "name" in values:
            self._check_name(values["name"], draft, where)
            draft.name = values["name"]
        if "user_id" in values:
            # like the service: only a changed link is checked, so a stale one left by a deleted user stays editable
            if values["user_id"] is not None and values["user_id"] != self.existing[member_id].user_id:
                self._check_user(values["user_id"], draft, where)
            draft.user_id = values["user_id"]
        for list_field in PROFILE_LIST_FIELDS:
            if list_field in values:
                draft.lists[list_field] = list(values[list_field])

    def create(self, data: MemberProfileCreate, where: str) -> None:
        self._check_name(data.name, None, where)
        if data.user_id is not None:
            self._check_user(data.user_id, None, where)
        self.drafts.append(_Draft(data.name, data.user_id, {f: list(getattr(data, f)) for f in PROFILE_LIST_FIELDS}))

    def resolve(self, member_ref: str, where: str) -> _Draft:
        """Same lookup as the service: an id first, then the name case-insensitively; never pick among several."""
        try:
            member_id: UUID | None = UUID(member_ref.strip())
        except ValueError:
            member_id = None
        if member_id is not None and (draft := self._draft(member_id)) is not None:
            return draft
        matches = [d for d in self.drafts if _key(d.name) == _key(member_ref)]
        if not matches:
            raise McpToolError(f"{where}: member not found: {member_ref}")
        if len(matches) > 1:
            raise McpToolError(f"{where}: several members are named {member_ref.strip()!r}; use the member id instead")
        return matches[0]


@dataclass
class _AddTo:
    member: str
    field: str
    values: list[str]


def _parse_add_to(batch: _Batch, add_to: Any) -> _AddTo:
    where = "add_to"
    fields = _check_keys(add_to, _ADD_TO_KEYS, where)
    missing = sorted(_ADD_TO_KEYS - set(fields))
    if missing:
        raise McpToolError(f"{where}: missing {', '.join(missing)}")
    member, list_field, values = fields["member"], fields["field"], fields["values"]
    if not isinstance(member, str) or not member.strip():
        raise McpToolError(f"{where}.member: give a member's name or id")
    if list_field not in PROFILE_LIST_FIELDS:
        raise McpToolError(f"{where}.field: must be one of {', '.join(PROFILE_LIST_FIELDS)}, got {list_field!r}")
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise McpToolError(f"{where}.values: expected a list of strings")
    if not _normalise(values, where):
        raise McpToolError(f"{where}.values: give at least one non-empty value")
    draft = batch.resolve(member, where)
    combined = _normalise([*draft.lists[list_field], *values], f"{where}: {draft.name}'s {list_field}")
    draft.lists[list_field] = combined
    return _AddTo(member, list_field, values)


def _normalise(values: list[str], where: str) -> list[str]:
    try:
        return normalise_list(values)
    except ValueError as e:
        raise McpToolError(f"{where}: {e}") from e


# ---------------------------------------------------------------------- update


def update_household_profile_impl(
    ctx: McpContext,
    members: list[dict[str, Any]] | None = None,
    remove_member_ids: list[str] | None = None,
    household: dict[str, Any] | None = None,
    add_to: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not members and not remove_member_ids and household is None and add_to is None:
        raise McpToolError("nothing to change: give members, remove_member_ids, household or add_to")

    service = HouseholdProfileService(ctx.repos, ctx.user)
    batch = _Batch(ctx, service.get().members)

    # 1. validate everything, replaying the batch in write order; nothing is written unless all of it is valid
    remove_ids = [_parse_member_id(member_id) for member_id in remove_member_ids or []]
    repeated = [str(i) for i, count in Counter(remove_ids).items() if count > 1]
    if repeated:
        raise McpToolError(f"remove_member_ids: repeated id(s) {', '.join(repeated)}")
    for member_id in remove_ids:
        if member_id not in batch.existing:
            raise not_found("member", str(member_id))
        batch.remove(member_id)

    updates: list[tuple[UUID, MemberProfileUpdate]] = []
    creates: list[MemberProfileCreate] = []
    entries = [(n, _check_keys(entry, _MEMBER_KEYS, f"members[{n}]")) for n, entry in enumerate(members or [])]
    to_update = [(n, fields) for n, fields in entries if "id" in fields]
    to_create = [(n, fields) for n, fields in entries if "id" not in fields]
    for n, fields in to_update:
        where = f"members[{n}]"
        raw_id = fields.pop("id")
        member_id = _parse_member_id(raw_id)
        if member_id in remove_ids:
            raise McpToolError(f"{where}: member {raw_id} is also in remove_member_ids")
        if member_id not in batch.existing:
            raise not_found("member", str(raw_id))
        if any(member_id == done for done, _ in updates):
            raise McpToolError(f"members: repeated id {raw_id}; put all changes to one member in a single entry")
        data = _validate(MemberProfileUpdate, fields, where)
        batch.update(member_id, data, where)
        updates.append((member_id, data))
    for n, fields in to_create:
        where = f"members[{n}]"
        data_create = _validate(MemberProfileCreate, fields, where)
        batch.create(data_create, where)
        creates.append(data_create)

    plan_add_to = _parse_add_to(batch, add_to) if add_to is not None else None

    preferences = (
        _validate(MealPreferencesUpdate, _check_keys(household, _HOUSEHOLD_KEYS, "household"), "household")
        if household is not None
        else None
    )

    # 2. apply in the order validated: removes, updates, creates, add_to, household
    try:
        for member_id in remove_ids:
            service.delete_member(member_id)
        for member_id, data in updates:
            service.update_member(member_id, data)
        for data_create in creates:
            service.create_member(data_create)
        if plan_add_to is not None:
            service.add_to_member(plan_add_to.member, cast(ProfileListField, plan_add_to.field), plan_add_to.values)
        if preferences is not None:
            service.update_preferences(preferences)
    except (ProfileConflict, NoEntryFound, ValueError) as e:
        # only reachable when the household's profiles changed between validation and write
        raise McpToolError(
            f"the profiles changed while saving: {e}; earlier changes in this call may be saved, "
            "call get_household_context and retry"
        ) from e

    return _preferences(ctx)


# ---------------------------------------------------------------------- tools


@mcp_server.tool()
@require_scope("recipes:read")
async def get_household_context() -> dict[str, Any]:
    """Call this first in every conversation. Returns the user's group and household, the household
    members (Mealie users), today's date (server time), the first day of the week (0 = Sunday), the
    locale, the scopes this connection was granted and the household `preferences`:
    {members: [{id, name, is_child, diet, allergies, exclusions, dislikes, likes, notes, is_current_user}],
    household: {default_servings, quick_weekdays, weeknight_max_minutes, weekend_max_minutes,
    favourite_cuisines, notes} | null}. `preferences.members` are the people who eat here (a Mealie user
    or just a name, such as a child); `is_current_user` marks the profile of the user you are talking to.
    Follow them when proposing meals: allergies and exclusions are hard constraints (never propose a
    recipe whose ingredients contain them; when unsure, check get_recipe's ingredients or ask); dislikes
    are soft (avoid unless the user asks); likes and favourite cuisines are hints. quick_weekdays (0 =
    Monday ... 6 = Sunday) are days to keep cooking short; weeknight_max_minutes and weekend_max_minutes
    bound a recipe's total time on those days."""
    return await run_in_context(get_household_context_impl)


@mcp_server.tool()
@require_scope("household:write")
async def update_household_profile(
    members: list[dict[str, Any]] | None = None,
    remove_member_ids: list[str] | None = None,
    household: dict[str, Any] | None = None,
    add_to: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record who eats here and how the household cooks. Never infer allergies: record an allergy only
    when the user states it.
    members: [{id?, name?, user_id?, is_child?, diet?, allergies?, exclusions?, dislikes?, likes?,
    notes?}]; an entry with `id` (from get_household_context) updates only the fields given (a list
    given replaces that list), one without `id` creates a member (`name` required, at most 60
    characters, unique ignoring case). diet is none, vegetarian, vegan, pescatarian, halal, kosher or
    other; user_id links a Mealie user of this household and `user_id: null` unlinks it; lists hold
    short strings (at most 60 characters, 30 entries, duplicates dropped) and are cleared by sending [],
    never null; `notes: null` clears the notes.
    remove_member_ids: [id].
    household: {default_servings? (1-20), quick_weekdays? ([0-6]), weeknight_max_minutes?,
    weekend_max_minutes? (5-480), favourite_cuisines?, notes?}; fields left out keep their value.
    quick_weekdays uses 0 = Monday ... 6 = Sunday, which is NOT the 0 = Sunday of get_household_context's
    first_day_of_week. Lists (quick_weekdays, favourite_cuisines) are cleared by sending [], never null;
    the other fields (default_servings, the max minutes, notes) are cleared by sending null.
    add_to: {member: name or id, field: "allergies"|"exclusions"|"dislikes"|"likes", values: [str]}
    appends to that list without replacing it; prefer it for what you learn in conversation ("Sam
    doesn't eat mushrooms").
    Meaning: allergies and exclusions are hard constraints (never propose a recipe containing them);
    dislikes are soft (avoid unless asked); likes and favourite cuisines are hints; quick weekdays and the
    max minutes bound total cooking time on those days.
    Everything is validated first; if anything is invalid (unknown key or id, duplicate name, ambiguous
    member) nothing is written. Applied in order: removals, updates, new members, add_to, household.
    Returns the updated preferences, shaped as in get_household_context."""
    return await run_in_context(update_household_profile_impl, members, remove_member_ids, household, add_to)
