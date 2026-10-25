from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel

from mealie.core.config import get_app_settings
from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext
from mealie.mcp.errors import not_found
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.mcp.tools._summaries import feedback_summaries, last_made_by_recipe, last_verdict, recipe_brief
from mealie.mcp.tools.recipes import _find_recipe
from mealie.schema.household.recipe_feedback import RecipeFeedbackSummary
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry, SavePlanEntry

MAX_RANGE_DAYS = 366


class MealplanEntryIn(BaseModel):
    date: date
    entry_type: PlanEntryType = PlanEntryType.dinner
    recipe_slug: str | None = None
    title: str = ""
    text: str = ""
    servings: float | None = None


def day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min, tzinfo=UTC), datetime.combine(end, time.min, tzinfo=UTC)


def _entry_dict(
    ctx: McpContext,
    entry: ReadPlanEntry,
    last_made: dict[Any, date],
    summaries: dict[Any, RecipeFeedbackSummary],
) -> dict[str, Any]:
    recipe = entry.recipe
    return {
        "id": entry.id,
        "date": entry.date.isoformat(),
        "entry_type": entry.entry_type.value,
        "title": entry.title,
        "text": entry.text,
        "cooked": entry.cooked_at is not None,
        "recipe": recipe_brief(
            recipe,
            last_made.get(recipe.id) if recipe.id else None,
            ctx.user.group_slug,
            last_verdict(summaries, recipe.id),
        )
        if recipe
        else None,
        "servings": entry.recipe_scale * recipe.recipe_servings if recipe and recipe.recipe_servings else None,
    }


def _entries(ctx: McpContext, entries: list[ReadPlanEntry]) -> list[dict[str, Any]]:
    recipe_ids = [e.recipe.id for e in entries if e.recipe and e.recipe.id]
    last_made = last_made_by_recipe(ctx.session, ctx.user.household_id, recipe_ids)
    summaries = feedback_summaries(ctx, recipe_ids)
    return [_entry_dict(ctx, e, last_made, summaries) for e in entries]


def get_mealplan_impl(ctx: McpContext, start_date: date, end_date: date) -> dict[str, Any]:
    start, end = day_bounds(start_date, end_date)
    entries = sorted(ctx.repos.meals.get_meals_by_date_range(start, end), key=lambda e: (e.date, e.id))
    return {"entries": _entries(ctx, entries)}


def get_recent_meals_impl(ctx: McpContext, days: int = 14) -> dict[str, Any]:
    days = min(max(days, 1), MAX_RANGE_DAYS)
    today = datetime.now().astimezone().date()
    start, end = day_bounds(today - timedelta(days=days), today)
    entries = sorted(ctx.repos.meals.get_meals_by_date_range(start, end), key=lambda e: (e.date, e.id), reverse=True)
    counts = Counter(e.recipe.slug for e in entries if e.recipe)
    return {"entries": _entries(ctx, entries), "recipe_counts": dict(counts)}


def add_mealplan_entries_impl(ctx: McpContext, entries: list[MealplanEntryIn]) -> dict[str, Any]:
    # Resolve and validate everything first so a bad entry leaves the plan untouched.
    to_save: list[SavePlanEntry] = []
    recipes_by_slug: dict[str, Any] = {}
    for entry in entries:
        recipe_id = None
        scale = 1.0
        if entry.recipe_slug:
            if entry.recipe_slug not in recipes_by_slug:
                recipe = _find_recipe(ctx, entry.recipe_slug)
                if recipe is None:
                    raise not_found("recipe", entry.recipe_slug)
                recipes_by_slug[entry.recipe_slug] = recipe
            recipe = recipes_by_slug[entry.recipe_slug]
            recipe_id = recipe.id
            if entry.servings and recipe.recipe_servings:
                scale = entry.servings / recipe.recipe_servings
        to_save.append(
            SavePlanEntry(
                date=entry.date,
                entry_type=entry.entry_type,
                title=entry.title,
                text=entry.text,
                recipe_id=recipe_id,
                recipe_scale=scale,
                group_id=ctx.user.group_id,
                user_id=ctx.user.id,
            )
        )

    created = [ctx.repos.meals.create(e) for e in to_save]
    return {
        "created": _entries(ctx, created),
        "mealplan_url": f"{get_app_settings().BASE_URL.rstrip('/')}/household/mealplan/planner/view",
    }


def remove_mealplan_entry_impl(ctx: McpContext, entry_id: int) -> dict[str, Any]:
    if ctx.repos.meals.get_one(entry_id) is None:
        raise not_found("mealplan_entry", str(entry_id))
    ctx.repos.meals.delete(entry_id)
    return {"removed": entry_id}


@mcp_server.tool()
@require_scope("recipes:read")
async def get_mealplan(start_date: date, end_date: date) -> dict[str, Any]:
    """Read the household meal plan between two dates (inclusive, YYYY-MM-DD). Returns
    {entries: [{id, date, entry_type, title, text, recipe, servings}]} ordered by date; `recipe` is
    null for free-text entries and `servings` is the planned servings when the recipe has a count."""
    return await run_in_context(get_mealplan_impl, start_date, end_date)


@mcp_server.tool()
@require_scope("recipes:read")
async def get_recent_meals(days: int = 14) -> dict[str, Any]:
    """What the household planned over the last `days` days (default 14, max 366), up to today, most
    recent first. Use it to avoid repeating dishes. Each entry's recipe has `last_verdict`, this
    household's latest feedback (loved, ok, never_again; null when none). Returns {entries,
    recipe_counts} where recipe_counts maps each recipe slug to how many times it appears. When the
    user says how one of these meals went, call record_recipe_feedback."""
    return await run_in_context(get_recent_meals_impl, days)


@mcp_server.tool()
@require_scope("mealplan:write")
async def add_mealplan_entries(entries: list[MealplanEntryIn]) -> dict[str, Any]:
    """Add entries to the household meal plan in one batch. Each entry has a `date` (YYYY-MM-DD), an
    `entry_type` (breakfast, lunch, dinner, side, snack, drink, dessert; default dinner) and either a
    `recipe_slug` (from search_recipes) or a free-text `title`, plus optional `text` and `servings`
    (scales the recipe from its own servings). All-or-nothing: an unknown recipe slug fails the whole
    batch and nothing is added. Returns {created, mealplan_url}."""
    return await run_in_context(add_mealplan_entries_impl, entries)


@mcp_server.tool()
@require_scope("mealplan:write")
async def remove_mealplan_entry(entry_id: int) -> dict[str, Any]:
    """Remove one entry from the household meal plan by its id (as returned by get_mealplan)."""
    return await run_in_context(remove_mealplan_entry_impl, entry_id)
