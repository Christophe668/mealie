from datetime import date
from typing import Any
from uuid import UUID

from mealie.core.config import get_app_settings
from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext, cross_household_repos
from mealie.mcp.errors import not_found
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.mcp.tools.mealplan import day_bounds
from mealie.schema.household.group_shopping_list import (
    ShoppingListAddRecipeParamsBulk,
    ShoppingListCreate,
    ShoppingListItemCreate,
    ShoppingListItemOut,
    ShoppingListItemUpdateBulk,
    ShoppingListOut,
)
from mealie.schema.response.pagination import OrderDirection, PaginationQuery
from mealie.services.household_services.shopping_lists import ShoppingListService


def _parse_id(kind: str, value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as e:
        raise not_found(kind, value) from e


def _load_list(ctx: McpContext, list_id: str | None) -> ShoppingListOut:
    if not list_id:
        page = ctx.repos.group_shopping_lists.page_all(
            PaginationQuery(page=1, per_page=1, order_by="updated_at", order_direction=OrderDirection.desc)
        )
        if not page.items:
            raise not_found("shopping_list", "(none)")
        return ctx.repos.group_shopping_lists.get_one(page.items[0].id) or page.items[0]  # type: ignore[return-value]

    shopping_list = ctx.repos.group_shopping_lists.get_one(_parse_id("shopping_list", list_id))
    if shopping_list is None:
        raise not_found("shopping_list", list_id)
    return shopping_list


def _item_dict(item: ShoppingListItemOut) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "checked": item.checked,
        "quantity": item.quantity,
        "unit": (item.unit.name if item.unit else None),
        "food": (item.food.name if item.food else None),
        "note": item.note,
        "label": (item.label.name if item.label else None),
        "display": item.display,
    }


def _list_dict(ctx: McpContext, shopping_list: ShoppingListOut) -> dict[str, Any]:
    items = sorted(
        shopping_list.list_items,
        key=lambda i: (i.label is None, i.label.name.lower() if i.label else "", i.position),
    )
    repos = cross_household_repos(ctx)
    references = []
    for ref in shopping_list.recipe_references:
        recipe = ref.recipe or repos.recipes.get_one(ref.recipe_id)
        references.append({"recipe_slug": recipe.slug if recipe else None, "quantity": ref.recipe_quantity})
    return {
        "id": str(shopping_list.id),
        "name": shopping_list.name,
        "url": f"{get_app_settings().BASE_URL.rstrip('/')}/shopping-lists/{shopping_list.id}",
        "items": [_item_dict(i) for i in items],
        "recipe_references": references,
    }


def get_shopping_list_impl(ctx: McpContext, list_id: str | None = None) -> dict[str, Any]:
    return _list_dict(ctx, _load_list(ctx, list_id))


def create_shopping_list_from_mealplan_impl(
    ctx: McpContext,
    start_date: date,
    end_date: date,
    list_name: str | None = None,
    list_id: str | None = None,
) -> dict[str, Any]:
    svc = ShoppingListService(ctx.repos)
    target = _load_list(ctx, list_id) if list_id else None

    start, end = day_bounds(start_date, end_date)
    entries = sorted(ctx.repos.meals.get_meals_by_date_range(start, end), key=lambda e: (e.date, e.id))
    with_recipe = [e for e in entries if e.recipe and e.recipe.id]
    without_recipe = [e.title or e.text for e in entries if not (e.recipe and e.recipe.id)]

    if target is None:
        target = svc.create_one_list(
            ShoppingListCreate(name=list_name or f"Shopping {start_date}–{end_date}"), owner_id=ctx.user.id
        )

    recipes_added: list[str] = []
    if with_recipe:
        params = [
            ShoppingListAddRecipeParamsBulk(recipe_id=e.recipe.id, recipe_increment_quantity=e.recipe_scale)  # type: ignore[union-attr]
            for e in with_recipe
        ]
        svc.add_recipe_ingredients_to_list(target.id, params)
        recipes_added = [e.recipe.slug for e in with_recipe]  # type: ignore[union-attr]

    result = _list_dict(ctx, _load_list(ctx, str(target.id)))
    result["recipes_added"] = recipes_added
    result["entries_without_recipe"] = without_recipe
    result["skipped_from_pantry"] = []
    return result


def add_shopping_items_impl(ctx: McpContext, list_id: str, items: list[str]) -> dict[str, Any]:
    shopping_list = _load_list(ctx, list_id)
    svc = ShoppingListService(ctx.repos)
    svc.bulk_create_items(
        [
            ShoppingListItemCreate(shopping_list_id=shopping_list.id, note=text, is_food=False, quantity=1)
            for text in items
        ]
    )
    return _list_dict(ctx, _load_list(ctx, list_id))


def check_shopping_items_impl(
    ctx: McpContext, list_id: str, item_ids: list[str], checked: bool = True
) -> dict[str, Any]:
    shopping_list = _load_list(ctx, list_id)
    updates: list[ShoppingListItemUpdateBulk] = []
    for item_id in item_ids:
        item = ctx.repos.group_shopping_list_item.get_one(_parse_id("shopping_list_item", item_id))
        if item is None or item.shopping_list_id != shopping_list.id:
            raise not_found("shopping_list_item", item_id)
        updates.append(item.cast(ShoppingListItemUpdateBulk, checked=checked))
    if updates:
        ShoppingListService(ctx.repos).bulk_update_items(updates)
    return _list_dict(ctx, _load_list(ctx, list_id))


@mcp_server.tool()
@require_scope("recipes:read")
async def get_shopping_list(list_id: str | None = None) -> dict[str, Any]:
    """Read a shopping list; without `list_id` the household's most recently updated list. Returns
    {id, name, url, items: [{id, checked, quantity, unit, food, note, label, display}], recipe_references:
    [{recipe_slug, quantity}]} with items sorted by label then position."""
    return await run_in_context(get_shopping_list_impl, list_id)


@mcp_server.tool()
@require_scope("shopping:write")
async def create_shopping_list_from_mealplan(
    start_date: date, end_date: date, list_name: str | None = None, list_id: str | None = None
) -> dict[str, Any]:
    """Turn the recipes planned between two dates (YYYY-MM-DD, inclusive) into a shopping list. Creates
    a new list (named `list_name`, default "Shopping <start>–<end>") or adds to the existing `list_id`,
    merging with items already there. Returns the list (see get_shopping_list) plus recipes_added
    (slugs, one per planned entry, so repeats are possible),
    entries_without_recipe (titles of free-text entries, not added) and
    skipped_from_pantry."""
    return await run_in_context(create_shopping_list_from_mealplan_impl, start_date, end_date, list_name, list_id)


@mcp_server.tool()
@require_scope("shopping:write")
async def add_shopping_items(list_id: str, items: list[str]) -> dict[str, Any]:
    """Add free-text items (e.g. "2 lemons") to a shopping list. Returns the updated list."""
    return await run_in_context(add_shopping_items_impl, list_id, items)


@mcp_server.tool()
@require_scope("shopping:write")
async def check_shopping_items(list_id: str, item_ids: list[str], checked: bool = True) -> dict[str, Any]:
    """Check (or with checked=false, uncheck) items on a shopping list by item id (from
    get_shopping_list). Unknown ids fail the whole call. Returns the updated list."""
    return await run_in_context(check_shopping_items_impl, list_id, item_ids, checked)
