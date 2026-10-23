from typing import Any, Literal
from uuid import UUID

from slugify import slugify

from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext, cross_household_repos
from mealie.mcp.errors import not_found
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.mcp.tools._summaries import last_made_by_recipe, recipe_brief, recipe_url
from mealie.repos.repository_generic import GroupRepositoryGeneric
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.response.pagination import OrderDirection, PaginationQuery
from mealie.services.query_filter.builder import QueryFilterBuilder

OrderBy = Literal["name", "rating", "random", "last_made", "created_at"]

MAX_PER_PAGE = 100

# Direction that makes each ordering useful for meal planning:
# best rated first, least recently made first, newest first.
_DIRECTIONS: dict[str, OrderDirection] = {
    "name": OrderDirection.asc,
    "rating": OrderDirection.desc,
    "random": OrderDirection.asc,
    "last_made": OrderDirection.asc,
    "created_at": OrderDirection.desc,
}


def _resolve_organizers(repo: GroupRepositoryGeneric, values: list[str]) -> tuple[list[UUID], list[str]]:
    """Maps tag/category names or slugs (group-scoped) to ids; returns (ids, unknown values)."""
    ids: list[UUID] = []
    unknown: list[str] = []
    for value in values:
        # slugs are unique per group; the name lookup covers names whose slug was edited
        item = repo.get_one(slugify(value), "slug") or repo.get_one(value, "name", any_case=True)
        if item is None:
            unknown.append(value)
        else:
            ids.append(item.id)
    return ids, unknown


def _build_filter(
    max_total_minutes: int | None, min_rating: float | None, not_made_since_days: int | None
) -> str | None:
    return (
        QueryFilterBuilder.combine_filters(
            f"total_time_seconds <= {int(max_total_minutes) * 60}" if max_total_minutes is not None else None,
            f"rating >= {float(min_rating)}" if min_rating is not None else None,
            # never-made recipes get a 1900-01-01 sentinel for last_made, so they pass this filter
            f"last_made <= $NOW-{int(not_made_since_days)}d" if not_made_since_days is not None else None,
        )
        or None
    )


def search_recipes_impl(
    ctx: McpContext,
    query: str | None = None,
    tags: list[str] | None = None,
    categories: list[str] | None = None,
    max_total_minutes: int | None = None,
    min_rating: float | None = None,
    not_made_since_days: int | None = None,
    order_by: OrderBy = "name",
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    page = max(page, 1)
    per_page = min(max(per_page, 1), MAX_PER_PAGE)
    repos = cross_household_repos(ctx)

    tag_ids, unknown_tags = _resolve_organizers(repos.tags, tags or [])
    category_ids, unknown_categories = _resolve_organizers(repos.categories, categories or [])
    if unknown_tags or unknown_categories:
        # An unknown organizer can never match; never silently drop it (that would widen the search).
        return {
            "items": [],
            "page": page,
            "per_page": per_page,
            "total": 0,
            "unknown_tags": unknown_tags,
            "unknown_categories": unknown_categories,
        }

    pagination = PaginationQuery(
        page=page,
        per_page=per_page,
        order_by=order_by,
        order_direction=_DIRECTIONS[order_by],
        query_filter=_build_filter(max_total_minutes, min_rating, not_made_since_days),
        pagination_seed=repos.recipes._random_seed() if order_by == "random" else None,
    )
    result = repos.recipes.by_user(ctx.user.id).page_all(
        pagination,
        tags=list(tag_ids) or None,
        categories=list(category_ids) or None,
        require_all_tags=True,
        require_all_categories=True,
        search=query or None,
    )

    last_made = last_made_by_recipe(ctx.session, ctx.user.household_id, [r.id for r in result.items if r.id])
    return {
        "items": [recipe_brief(r, last_made.get(r.id) if r.id else None, ctx.user.group_slug) for r in result.items],
        "page": result.page,
        "per_page": result.per_page,
        "total": result.total,
    }


def _find_recipe(ctx: McpContext, slug_or_id: str) -> Recipe | None:
    repo = cross_household_repos(ctx).recipes
    recipe = repo.get_one(slug_or_id, "slug")
    if recipe is not None:
        return recipe
    try:
        recipe_id = UUID(slug_or_id)
    except ValueError:
        return None
    return repo.get_one(recipe_id, "id")


def get_recipe_impl(ctx: McpContext, slug_or_id: str) -> dict[str, Any]:
    recipe = _find_recipe(ctx, slug_or_id)
    if recipe is None:
        raise not_found("recipe", slug_or_id)

    return {
        "id": str(recipe.id),
        "name": recipe.name,
        "slug": recipe.slug,
        "description": recipe.description,
        "servings": recipe.recipe_servings or None,
        "yield": recipe.recipe_yield,
        "times": {"total": recipe.total_time, "prep": recipe.prep_time, "cook": recipe.perform_time},
        "ingredients": [
            {
                "quantity": i.quantity,
                "unit": i.unit.name if i.unit else None,
                "food": i.food.name if i.food else None,
                "note": i.note,
                "display": i.display,
            }
            for i in recipe.recipe_ingredient
        ],
        "instructions": [{"title": s.title, "text": s.text} for s in recipe.recipe_instructions or []],
        "tags": [t.name for t in recipe.tags or []],
        "categories": [c.name for c in recipe.recipe_category or []],
        "tools": [t.name for t in recipe.tools],
        "notes": [{"title": n.title, "text": n.text} for n in recipe.notes or []],
        "org_url": recipe.org_url,
        "url": recipe_url(ctx.user.group_slug, recipe.slug),
    }


@mcp_server.tool()
@require_scope("recipes:read")
async def search_recipes(
    query: str | None = None,
    tags: list[str] | None = None,
    categories: list[str] | None = None,
    max_total_minutes: int | None = None,
    min_rating: float | None = None,
    not_made_since_days: int | None = None,
    order_by: OrderBy = "name",
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    """Search recipes across every household of the user's group, to pick what to cook.
    Filters combine with AND: free-text `query`, tag/category names (all must match), max total time,
    min rating, and "not made by this household in N days". `order_by` "rating" is best first,
    "last_made" least recent first, "random" a fresh shuffle. Returns {items, page, per_page, total}
    with short summaries; call get_recipe for ingredients and steps."""
    return await run_in_context(
        search_recipes_impl,
        query=query,
        tags=tags,
        categories=categories,
        max_total_minutes=max_total_minutes,
        min_rating=min_rating,
        not_made_since_days=not_made_since_days,
        order_by=order_by,
        page=page,
        per_page=per_page,
    )


@mcp_server.tool()
@require_scope("recipes:read")
async def get_recipe(slug_or_id: str) -> dict[str, Any]:
    """Fetch one recipe in full by slug or id (as returned by search_recipes): servings, times,
    ingredients, instructions, tags, categories, tools, notes, source URL and the Mealie page URL.
    Use it before planning or shopping for a recipe."""
    return await run_in_context(get_recipe_impl, slug_or_id)
