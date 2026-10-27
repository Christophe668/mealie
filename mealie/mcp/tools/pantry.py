import re
from collections import Counter
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from mealie.core.exceptions import NoEntryFound
from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext
from mealie.mcp.errors import McpToolError, not_found
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import _clock, run_in_context
from mealie.mcp.tools._validation import check_keys, parse_uuid
from mealie.mcp.tools.recipes import _find_recipe
from mealie.schema.household.cooked_meal import (
    CookedLeftovers,
    CookedMealCreate,
    CookedPantryOutcome,
    PantryOutcome,
)
from mealie.schema.household.pantry import PantryItemCreate, PantryItemOut, PantryItemUpdate, PantryLocation
from mealie.schema.recipe.recipe_ingredient import IngredientUnit
from mealie.services.claude_context.cooked_meal_service import (
    LEFTOVER_PORTIONS_MAX,
    LEFTOVER_PORTIONS_MIN,
    AlreadyCookedError,
    CookedMealService,
    PantryItemNotInRecipeError,
)
from mealie.services.claude_context.pantry_service import PantryItemsNotChecked, PantryService
from mealie.services.claude_context.recipe_feedback_service import FutureMadeOnError

_ITEM_FIELDS = frozenset(PantryItemCreate.model_fields)
# `unit` is accepted as a unit name (or abbreviation) and resolved to `unit_id`.
_ADD_KEYS = _ITEM_FIELDS | {"unit"}
_UPDATE_KEYS = _ADD_KEYS | {"id"}
_SHELF_LIFE_KEYS = ("shelf_life_days_opened", "shelf_life_days_unopened")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_OUTCOMES = ", ".join(o.value for o in PantryOutcome)
_PANTRY_OUTCOME_KEYS = frozenset({"id", "outcome", "quantity", "replaces_reference_id"})


def _parse_id(kind: str, value: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as e:
        raise not_found(kind, str(value)) from e


def _days(start: date | None, end: date | None) -> int | None:
    return (end - start).days if start is not None and end is not None else None


def _shelf_life(extras: dict | None, key: str) -> int | None:
    """An integer shelf life from the food's extras; extras are stored as strings, so numeric strings count."""
    value = (extras or {}).get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _item_dict(item: PantryItemOut, today: date) -> dict[str, Any]:
    extras = item.food.extras if item.food else None
    return {
        "id": str(item.id),
        "name": item.name,
        "food_id": str(item.food_id) if item.food_id else None,
        "quantity": item.quantity,
        "unit": item.unit.name if item.unit else None,
        "location": item.location.value,
        "bought_on": item.bought_on.isoformat() if item.bought_on else None,
        "opened_on": item.opened_on.isoformat() if item.opened_on else None,
        "use_by": item.use_by.isoformat() if item.use_by else None,
        "source": item.source.value,
        "note": item.note,
        "days_since_bought": _days(item.bought_on, today),
        "days_since_opened": _days(item.opened_on, today),
        "days_until_use_by": _days(today, item.use_by),
        "shelf_life_days_opened": _shelf_life(extras, _SHELF_LIFE_KEYS[0]),
        "shelf_life_days_unopened": _shelf_life(extras, _SHELF_LIFE_KEYS[1]),
    }


def _parse_location(location: str | None) -> PantryLocation | None:
    if location is None:
        return None
    try:
        return PantryLocation(location)
    except ValueError as e:
        valid = ", ".join(loc.value for loc in PantryLocation)
        raise McpToolError(f"invalid location {location!r}; valid values: {valid}") from e


def _pantry_items(ctx: McpContext, location: PantryLocation | None = None) -> list[dict[str, Any]]:
    today = _clock.today()
    return [_item_dict(item, today) for item in PantryService(ctx.repos).list_items(location)]


# ---------------------------------------------------------------------- validation


class _UnitLookup:
    """Resolves unit names for one call, loading the group's units at most once."""

    def __init__(self, ctx: McpContext):
        self._ctx = ctx
        self._units: list[IngredientUnit] | None = None

    def resolve(self, fields: dict[str, Any], where: str) -> None:
        """Turns a `unit` name into `unit_id` (case-insensitive match on name, plural or abbreviation)."""
        if "unit" not in fields:
            return
        if "unit_id" in fields:
            raise McpToolError(f"{where}: give either unit or unit_id, not both")
        name = fields.pop("unit")
        if name is None:
            fields["unit_id"] = None
            return
        if self._units is None:
            self._units = self._ctx.repos.ingredient_units.get_all()
        wanted = str(name).strip().casefold()
        for unit in self._units:
            names = (unit.name, unit.plural_name, unit.abbreviation, unit.plural_abbreviation)
            if any(n and n.strip().casefold() == wanted for n in names):
                fields["unit_id"] = unit.id
                return
        raise McpToolError(f"{where}: unit not found: {name}")


def _duplicates(ids: list[UUID]) -> list[str]:
    counts = Counter(ids)
    return [str(i) for i in dict.fromkeys(ids) if counts[i] > 1]


def _validate[M: PantryItemCreate](model: type[M], fields: dict[str, Any], where: str) -> M:
    try:
        return model.model_validate(fields)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(str(p) for p in err['loc']) or 'entry'}: {err['msg']}" for err in e.errors())
        raise McpToolError(f"{where}: {problems}") from e


def _check_references(
    ctx: McpContext, data: PantryItemCreate, where: str, existing: PantryItemOut | None = None
) -> None:
    """Refuse foods/units outside the group up front, so no write happens before the error. On an update only
    changed references are checked (a deleted food can leave a dangling id that must stay editable)."""
    food_id, unit_id = data.food_id, data.unit_id
    if existing is not None:
        food_id = food_id if food_id != existing.food_id else None
        unit_id = unit_id if unit_id != existing.unit_id else None
    if food_id is not None and ctx.repos.ingredient_foods.get_one(food_id) is None:
        raise McpToolError(f"{where}: food not found: {food_id}")
    if unit_id is not None and ctx.repos.ingredient_units.get_one(unit_id) is None:
        raise McpToolError(f"{where}: unit not found: {unit_id}")


# ---------------------------------------------------------------------- impls


def get_pantry_impl(ctx: McpContext, location: str | None = None) -> dict[str, Any]:
    return {"items": _pantry_items(ctx, _parse_location(location))}


def update_pantry_impl(
    ctx: McpContext,
    add: list[dict[str, Any]] | None = None,
    update: list[dict[str, Any]] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    service = PantryService(ctx.repos)
    units = _UnitLookup(ctx)

    # 1. validate everything; nothing is written unless every entry is valid
    remove_ids = [_parse_id("pantry_item", item_id) for item_id in remove or []]
    if repeated := _duplicates(remove_ids):
        raise McpToolError(f"remove: repeated id(s) {', '.join(repeated)}")
    for item_id in remove_ids:
        if ctx.repos.pantry_items.get_one(item_id) is None:
            raise not_found("pantry_item", str(item_id))

    updates: list[tuple[UUID, PantryItemUpdate]] = []
    for n, entry in enumerate(update or []):
        where = f"update[{n}]"
        fields = check_keys(entry, _UPDATE_KEYS, where)
        if "id" not in fields:
            raise McpToolError(f"{where}: missing id")
        raw_id = fields.pop("id")
        item_id = _parse_id("pantry_item", raw_id)
        if any(item_id == done for done, _ in updates):
            raise McpToolError(f"update: repeated id {raw_id}; put all changes to one item in a single entry")
        if item_id in remove_ids:
            raise McpToolError(f"{where}: pantry item {raw_id} is also in remove")
        existing = ctx.repos.pantry_items.get_one(item_id)
        if existing is None:
            raise not_found("pantry_item", str(raw_id))
        units.resolve(fields, where)
        # partial update: fields not given keep their current value
        current = existing.model_dump(include=set(_ITEM_FIELDS))
        changes = _validate(PantryItemUpdate, current | fields, where)
        _check_references(ctx, changes, where, existing)
        updates.append((item_id, changes))

    adds: list[PantryItemCreate] = []
    for n, entry in enumerate(add or []):
        where = f"add[{n}]"
        fields = check_keys(entry, _ADD_KEYS, where)
        units.resolve(fields, where)
        data = _validate(PantryItemCreate, fields, where)
        _check_references(ctx, data, where)
        adds.append(data)

    # 2. apply: removes, then updates, then adds
    added_ids: list[str] = []
    merged_ids: list[str] = []
    # only reachable if the pantry changed between validation and write; report the id being written
    writing: UUID | None = None
    try:
        for writing in remove_ids:
            service.remove_item(writing)
        for writing, data in updates:
            service.update_item(writing, data)
        writing = None
        for data in adds:
            item, merged = service.add_item(data)
            target = merged_ids if merged else added_ids
            if str(item.id) not in merged_ids and str(item.id) not in added_ids:
                target.append(str(item.id))
    except NoEntryFound as e:
        if writing is None:
            raise McpToolError(str(e)) from e
        raise not_found("pantry_item", str(writing)) from e

    return {
        "items": _pantry_items(ctx),
        "added_ids": added_ids,
        "merged_ids": merged_ids,
        "updated_ids": [str(item_id) for item_id, _ in updates],
        "removed_ids": [str(item_id) for item_id in remove_ids],
    }


def put_away_impl(ctx: McpContext, list_id: str, item_ids: list[str] | None = None) -> dict[str, Any]:
    list_uuid = _parse_id("shopping_list", list_id)
    if ctx.repos.group_shopping_lists.get_one(list_uuid) is None:
        raise not_found("shopping_list", list_id)
    ids = None if item_ids is None else [_parse_id("shopping_list_item", item_id) for item_id in item_ids]
    today = _clock.today()
    try:
        result = PantryService(ctx.repos).put_away(list_uuid, ids, today=today)
    except PantryItemsNotChecked as e:
        raise McpToolError(
            f"these items are not checked, so they were not put away (nothing was moved): {', '.join(e.item_ids)}; "
            "check them first or leave them out"
        ) from e
    except NoEntryFound as e:  # an item id that is not on this list
        raise McpToolError(str(e)) from e
    return {
        "created": [_item_dict(item, today) for item in result.created],
        "merged": [_item_dict(item, today) for item in result.merged],
        "removed_item_ids": [str(item_id) for item_id in result.removed_item_ids],
    }


def _parse_iso_date(name: str, value: str | None) -> date | None:
    if value is None:
        return None
    try:
        # date.fromisoformat also takes 20261020 and week dates; only YYYY-MM-DD is promised
        if not _ISO_DATE.fullmatch(value):
            raise ValueError(value)
        return date.fromisoformat(value)
    except ValueError as e:
        raise McpToolError(f"{name} must be an ISO date (YYYY-MM-DD), got {value!r}") from e


def _parse_outcomes(pantry: list[dict[str, Any]] | None) -> list[CookedPantryOutcome]:
    outcomes: list[CookedPantryOutcome] = []
    for n, entry in enumerate(pantry or []):
        where = f"pantry[{n}]"
        fields = check_keys(entry, _PANTRY_OUTCOME_KEYS, where)
        if "id" not in fields or "outcome" not in fields:
            raise McpToolError(f"{where}: needs id and outcome ({_OUTCOMES})")
        try:
            outcome = PantryOutcome(fields["outcome"])
        except ValueError as e:
            raise McpToolError(f"{where}: outcome must be one of {_OUTCOMES}, got {fields['outcome']!r}") from e
        quantity = fields.get("quantity")
        if "quantity" in fields:
            if isinstance(quantity, bool) or not isinstance(quantity, int | float) or quantity < 0:
                raise McpToolError(f"{where}: quantity must be a non-negative number, got {quantity!r}")
            if outcome is not PantryOutcome.some_left:
                raise McpToolError(f"{where}: quantity only goes with some_left")
        replaces = fields.get("replaces_reference_id")
        outcomes.append(
            CookedPantryOutcome(
                pantry_item_id=_parse_id("pantry_item", fields["id"]),
                outcome=outcome,
                quantity=quantity,
                replaces_reference_id=(
                    parse_uuid(where, "replaces_reference_id", replaces) if replaces is not None else None
                ),
            )
        )
    return outcomes


def _parse_leftovers(portions: int | None, location: str | None, use_by: str | None) -> CookedLeftovers | None:
    use_by_date = _parse_iso_date("leftover_use_by", use_by)
    if portions is None:
        if location is not None or use_by_date is not None:
            raise McpToolError("leftover_location and leftover_use_by need leftover_portions")
        return None
    if isinstance(portions, bool) or not isinstance(portions, int):
        raise McpToolError(f"leftover_portions must be a whole number, got {portions!r}")
    if not LEFTOVER_PORTIONS_MIN <= portions <= LEFTOVER_PORTIONS_MAX:
        raise McpToolError(f"leftover_portions must be {LEFTOVER_PORTIONS_MIN}-{LEFTOVER_PORTIONS_MAX}, got {portions}")
    if location is not None and location not in ("fridge", "freezer"):
        raise McpToolError(f"leftover_location must be fridge or freezer, got {location!r}")
    return CookedLeftovers(portions=portions, location=location or "fridge", use_by=use_by_date)  # type: ignore[arg-type]


def record_meal_cooked_impl(
    ctx: McpContext,
    recipe: str,
    cooked_on: str | None = None,
    meal_plan_entry_id: int | None = None,
    pantry: list[dict[str, Any]] | None = None,
    leftover_portions: int | None = None,
    leftover_location: str | None = None,
    leftover_use_by: str | None = None,
) -> dict[str, Any]:
    # validate every argument before the first write
    day = _parse_iso_date("cooked_on", cooked_on) or _clock.today()
    outcomes = _parse_outcomes(pantry)
    leftovers = _parse_leftovers(leftover_portions, leftover_location, leftover_use_by)
    found = _find_recipe(ctx, recipe)
    if found is None:
        raise not_found("recipe", recipe)
    names = {item.id: item.name for item in ctx.repos.pantry_items.ordered()}

    service = CookedMealService(ctx.repos, ctx.user, ctx.household)
    try:
        result = service.record(
            CookedMealCreate(
                recipe_id=found.id,
                cooked_on=day,
                meal_plan_entry_id=meal_plan_entry_id,
                pantry=outcomes,
                leftovers=leftovers,
            ),
            today=_clock.today(),
        )
    except FutureMadeOnError as e:
        raise McpToolError(f"cooked_on is in the future: {e}") from e
    except AlreadyCookedError as e:
        raise McpToolError(
            f"{e}. If the user wants to change the pantry or add leftovers anyway, use update_pantry."
        ) from e
    except (PantryItemNotInRecipeError, NoEntryFound) as e:
        raise McpToolError(str(e)) from e

    entry = result.meal_plan_entry
    leftover = result.leftover
    return {
        "meal_plan_entry": {
            "id": entry.id,
            "date": entry.date.isoformat(),
            "title": entry.title or (entry.recipe.name if entry.recipe else ""),
        }
        if entry
        else None,
        "removed": [names[item_id] for item_id in result.removed_item_ids if item_id in names],
        "kept": [item.name for item in result.kept_items],
        "leftover": {
            "id": str(leftover.id),
            "name": leftover.name,
            "portions": leftover.quantity,
            "location": leftover.location.value,
            "use_by": leftover.use_by.isoformat() if leftover.use_by else None,
        }
        if leftover
        else None,
    }


# ---------------------------------------------------------------------- tools


@mcp_server.tool()
@require_scope("recipes:read")
async def get_pantry(location: str | None = None) -> dict[str, Any]:
    """Read what the household has at home, soonest-to-use first (earliest use_by, then most recently
    bought). `location` limits it to one of fridge, freezer, cupboard, other. Returns {items: [{id, name,
    food_id, quantity, unit, location, bought_on, opened_on, use_by, source (shopping|manual|leftover), note,
    days_since_bought, days_since_opened, days_until_use_by, shelf_life_days_opened,
    shelf_life_days_unopened}]}. Dates are ISO (YYYY-MM-DD); day counts and shelf lives are integers or null
    (shelf lives are the food's typical keeping time in days, opened or unopened, when known). Freshness is
    your estimate from these dates and the food's shelf life: say so, present it as guidance rather than
    safety advice, and flag borderline cases instead of deciding them."""
    return await run_in_context(get_pantry_impl, location)


@mcp_server.tool()
@require_scope("pantry:write")
async def update_pantry(
    add: list[dict[str, Any]] | None = None,
    update: list[dict[str, Any]] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Change the pantry in one call: removes, then updates, then adds. Every entry is validated first; if
    any is invalid (unknown key, bad date, unknown id) nothing is written.
    add: [{name, food_id?, quantity?, unit?, location?, bought_on?, opened_on?, use_by?, source?, note?}];
    `unit` is a unit name, location is fridge|freezer|cupboard|other (default cupboard), source is
    manual|leftover|shopping (default manual). An addition matching an existing item (same food, or same
    name without a food) merges into it.
    update: [{id, ...any of the same fields}]; fields left out keep their value, null clears one.
    remove: [id].
    Dates are ISO (YYYY-MM-DD). When the user says they opened something, set its opened_on (today unless
    they say otherwise). Returns {items (the whole pantry, as get_pantry), added_ids, merged_ids, updated_ids,
    removed_ids}. Freshness stays your estimate from the dates and shelf life; present it as guidance."""
    return await run_in_context(update_pantry_impl, add, update, remove)


@mcp_server.tool()
@require_scope("pantry:write")
async def put_away_shopping_items(list_id: str, item_ids: list[str] | None = None) -> dict[str, Any]:
    """Put the bought shopping away: moves checked items of a shopping list into the pantry (bought_on
    today, location from the item's label) and deletes them from the list. Without `item_ids`, every checked
    item; with ids, all must be checked or nothing moves. Items matching an existing pantry item merge into
    it. Returns {created, merged, removed_item_ids}, pantry items shaped as in get_pantry (dates ISO
    YYYY-MM-DD)."""
    return await run_in_context(put_away_impl, list_id, item_ids)


@mcp_server.tool()
@require_scope("pantry:write")
async def record_meal_cooked(
    recipe: str,
    cooked_on: str | None = None,
    meal_plan_entry_id: int | None = None,
    pantry: list[dict[str, Any]] | None = None,
    leftover_portions: int | None = None,
    leftover_location: Literal["fridge", "freezer"] | None = None,
    leftover_use_by: str | None = None,
) -> dict[str, Any]:
    """Record that a meal was cooked. Call it when the user says a meal was cooked ("we had the carbonara
    tonight"); check get_recent_meals first so a meal is not recorded twice (a second recording for the same
    recipe and day is refused). `recipe` is a slug or id; `cooked_on` is an ISO date YYYY-MM-DD (default
    today, at most tomorrow). It marks the matching meal plan entry done (the household's not-yet-done entry
    for this recipe on that day or the day before, or `meal_plan_entry_id`) and moves the recipe's last made
    date forward. Ask the user about the `in_pantry` items that get_recipe lists and about leftovers, unless
    their own instructions say otherwise; nothing in the pantry changes without an explicit answer.
    pantry: [{id, outcome: "used_up"|"some_left", quantity?, replaces_reference_id?}] for items listed in
    get_recipe's in_pantry. Show the user the proposed changes (each item's proposed_quantity and
    proposed_outcome) before recording, and record what they confirm or correct: used_up removes the item,
    some_left keeps it (and sets opened_on to the cooking date if it was not opened) and, with `quantity`
    (the amount left, in the item's unit, 0 or more; send it from proposed_quantity or the user's correction),
    sets the item's quantity. Leave an item out to leave it alone, which is what a proposed_outcome of "none"
    means. When the item stood in for a recipe ingredient (a substitute), send that ingredient's `ref` as
    replaces_reference_id. leftover_portions (1-50, get_recipe's suggested_leftover_portions is a starting
    point) adds a "Leftover <recipe>" pantry item in leftover_location (fridge, default, or freezer) with
    leftover_use_by (ISO date; default 3 days after cooking for the fridge, 90 for the freezer). Call
    record_recipe_feedback only if the user said how it went. Returns {meal_plan_entry: {id, date, title} or
    null, removed: [names], kept: [names], leftover: {id, name, portions, location, use_by} or null};
    meal_plan_entry null means no plan entry was found, which is not an error. Nothing is written when an
    argument is refused."""
    return await run_in_context(
        record_meal_cooked_impl,
        recipe,
        cooked_on,
        meal_plan_entry_id,
        pantry,
        leftover_portions,
        leftover_location,
        leftover_use_by,
    )
