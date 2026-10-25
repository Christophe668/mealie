from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

from slugify import slugify
from sqlalchemy.exc import MultipleResultsFound

from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext, cross_household_repos
from mealie.mcp.errors import McpToolError, not_found
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.mcp.tools._summaries import (
    feedback_dict,
    feedback_service,
    feedback_summaries,
    last_made_by_recipe,
    last_verdict,
    recipe_brief,
    recipe_url,
    summary_dict,
    time_text,
)
from mealie.repos.repository_generic import GroupRepositoryGeneric
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.response.pagination import OrderByNullPosition, OrderDirection, PaginationQuery
from mealie.services.claude_context.recipe_writer import timer_minutes
from mealie.services.query_filter.builder import QueryFilterBuilder

OrderBy = Literal["name", "rating", "random", "last_made", "created_at"]

MAX_PER_PAGE = 100
# Latest household feedback entries returned with a full recipe.
RECIPE_FEEDBACK_LIMIT = 5

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
        try:
            item = repo.get_one(slugify(value), "slug") or repo.get_one(value, "name", any_case=True)
        except MultipleResultsFound as e:
            raise McpToolError(f"ambiguous tag or category: {value!r} matches several; use its slug") from e
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


def _build_pagination(
    order_by: OrderBy, page: int, per_page: int, query_filter: str | None, seed: Callable[[], str]
) -> PaginationQuery:
    return PaginationQuery(
        page=page,
        per_page=per_page,
        order_by=order_by,
        order_direction=_DIRECTIONS[order_by],
        # unrated recipes have a NULL rating; Postgres sorts NULLs first on DESC, so pin them last everywhere
        order_by_null_position=OrderByNullPosition.last,
        query_filter=query_filter,
        pagination_seed=seed() if order_by == "random" else None,
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

    pagination = _build_pagination(
        order_by,
        page,
        per_page,
        _build_filter(max_total_minutes, min_rating, not_made_since_days),
        repos.recipes._random_seed,
    )
    result = repos.recipes.by_user(ctx.user.id).page_all(
        pagination,
        tags=list(tag_ids) or None,
        categories=list(category_ids) or None,
        require_all_tags=True,
        require_all_categories=True,
        search=query or None,
    )

    recipe_ids = [r.id for r in result.items if r.id]
    last_made = last_made_by_recipe(ctx.session, ctx.user.household_id, recipe_ids)
    summaries = feedback_summaries(ctx, recipe_ids)
    return {
        "items": [
            recipe_brief(r, last_made.get(r.id) if r.id else None, ctx.user.group_slug, last_verdict(summaries, r.id))
            for r in result.items
        ],
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

    service = feedback_service(ctx)
    feedback = service.list(recipe.id, page=1, per_page=RECIPE_FEEDBACK_LIMIT).items
    summary = service.summaries([recipe.id]).get(recipe.id) if recipe.id else None
    # link rows have no stored order (PostgreSQL returns them in any order):
    # list them as the recipe lists its ingredients
    position = {str(i.reference_id): n for n, i in enumerate(recipe.recipe_ingredient)}
    return {
        "id": str(recipe.id),
        "name": recipe.name,
        "slug": recipe.slug,
        "description": recipe.description,
        "servings": recipe.recipe_servings or None,
        "yield": recipe.recipe_yield,
        "times": {
            "total": time_text(recipe.total_time, recipe.total_time_seconds),
            "prep": time_text(recipe.prep_time, recipe.prep_time_seconds),
            "cook": time_text(recipe.perform_time, recipe.perform_time_seconds),
        },
        "ingredients": [
            {
                "quantity": i.quantity,
                "unit": i.unit.name if i.unit else None,
                "food": i.food.name if i.food else None,
                "note": i.note,
                "display": i.display,
                # identity and section, for update_recipe to send back
                "ref": str(i.reference_id),
                "section": i.title or None,
            }
            for i in recipe.recipe_ingredient
        ],
        "instructions": [
            {
                "title": s.title,
                "text": s.text,
                "timer_minutes": timer_minutes(s.duration_seconds),
                "uses": sorted(
                    (str(r.reference_id) for r in s.ingredient_references if r.reference_id),
                    key=lambda ref: position.get(ref, len(position)),
                ),
            }
            for s in recipe.recipe_instructions or []
        ],
        "tags": [t.name for t in recipe.tags or []],
        "categories": [c.name for c in recipe.recipe_category or []],
        "tools": [t.name for t in recipe.tools],
        "notes": [{"title": n.title, "text": n.text} for n in recipe.notes or []],
        "org_url": recipe.org_url,
        "url": recipe_url(ctx.user.group_slug, recipe.slug),
        "feedback": [feedback_dict(row) for row in feedback],
        "feedback_summary": summary_dict(summary),
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
    Filters combine with AND: free-text `query`, tags/categories by name or slug (all must match),
    max total time, min rating, and "not made by this household in N days". Unknown tags/categories
    return total 0 with `unknown_tags`/`unknown_categories` listing them. `order_by` "rating" is best
    first (unrated last), "last_made" least recent first, "random" a fresh shuffle. `per_page` is
    capped at 100. `min_rating` and rating order use the caller's own rating when set, while `rating`
    in each item is the recipe's average. Each item has `last_verdict`, this household's latest
    feedback (loved, ok, never_again; null when none): do not propose a `never_again` recipe again
    unless the user asks for it, and prefer `loved` ones when the user wants something reliable.
    Returns {items, page, per_page, total}; call get_recipe for ingredients and steps."""
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
    ingredients, instructions, tags, categories, tools, notes, source URL and the Mealie page URL,
    plus this household's `feedback` (latest 5, newest first) and `feedback_summary` (last verdict,
    last made on, counts per verdict; null when there is none). Use it before planning or shopping
    for a recipe."""
    return await run_in_context(get_recipe_impl, slug_or_id)
