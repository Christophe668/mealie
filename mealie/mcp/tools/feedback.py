from datetime import date
from typing import Any

from mealie.core.exceptions import NoEntryFound
from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext
from mealie.mcp.errors import McpToolError, not_found
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.mcp.tools._summaries import feedback_dict, feedback_service, summary_dict
from mealie.mcp.tools.recipes import _find_recipe
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackCreate
from mealie.schema.recipe.recipe import Recipe

MAX_FEEDBACK_LIMIT = 50
_VERDICTS = ", ".join(v.value for v in FeedbackVerdict)


def _parse_verdict(verdict: str) -> FeedbackVerdict:
    try:
        return FeedbackVerdict(verdict)
    except ValueError as e:
        raise McpToolError(f"verdict must be one of {_VERDICTS}, got {verdict!r}") from e


def _parse_effort(effort: int | None) -> int | None:
    if effort is None:
        return None
    if isinstance(effort, bool) or not isinstance(effort, int) or not 1 <= effort <= 3:
        raise McpToolError(f"effort must be 1 (easy), 2 (fine) or 3 (a lot of work), got {effort!r}")
    return effort


def _parse_made_on(made_on: str | None) -> date | None:
    if made_on is None:
        return None
    try:
        return date.fromisoformat(made_on)
    except ValueError as e:
        raise McpToolError(f"made_on must be an ISO date (YYYY-MM-DD), got {made_on!r}") from e


def _recipe_or_raise(ctx: McpContext, recipe: str) -> Recipe:
    found = _find_recipe(ctx, recipe)
    if found is None:
        raise not_found("recipe", recipe)
    return found


def record_recipe_feedback_impl(
    ctx: McpContext,
    recipe: str,
    verdict: str,
    effort: int | None = None,
    note: str | None = None,
    for_whom: str | None = None,
    made_on: str | None = None,
) -> dict[str, Any]:
    # Validate every argument before the first write.
    data_verdict = _parse_verdict(verdict)
    data_effort = _parse_effort(effort)
    data_made_on = _parse_made_on(made_on)
    found = _recipe_or_raise(ctx, recipe)

    service = feedback_service(ctx)
    try:
        row = service.record(
            RecipeFeedbackCreate(
                recipe_id=found.id,
                verdict=data_verdict,
                effort=data_effort,
                note=note or None,
                for_whom=for_whom or None,
                made_on=data_made_on,
            )
        )
    except NoEntryFound as e:
        raise not_found("recipe", recipe) from e

    return {
        "feedback": feedback_dict(row),
        "summary": summary_dict(service.summaries([row.recipe_id]).get(row.recipe_id)),
    }


def get_recipe_feedback_impl(ctx: McpContext, recipe: str | None = None, limit: int = 10) -> dict[str, Any]:
    limit = min(max(limit, 1), MAX_FEEDBACK_LIMIT)
    recipe_id = _recipe_or_raise(ctx, recipe).id if recipe else None
    result = feedback_service(ctx).list(recipe_id, page=1, per_page=limit)
    return {"items": [feedback_dict(row) for row in result.items], "total": result.total}


@mcp_server.tool()
@require_scope("recipes:write")
async def record_recipe_feedback(
    recipe: str,
    verdict: str,
    effort: int | None = None,
    note: str | None = None,
    for_whom: str | None = None,
    made_on: str | None = None,
) -> dict[str, Any]:
    """Record how a meal went, for this household. Call it whenever the user says how a meal went
    ("the kids loved the lasagne", "never again", "too much work").
    `recipe` is a slug or id (from search_recipes, get_recipe or get_recent_meals).
    `verdict` is "loved", "ok" or "never_again"; `never_again` means do not propose the recipe again
    unless the user asks for it, and `loved` recipes are the ones to prefer when the user wants
    something reliable. Optional: `effort` 1 (easy), 2 (fine) or 3 (a lot of work); a free-text
    `note`; `for_whom` (who it was cooked for); `made_on` as an ISO date YYYY-MM-DD (default today).
    It also sets the user's rating (loved 5, ok 3, never_again 1), adds a timeline comment and moves
    the household's last made forward. Returns {feedback, summary} where summary is the recipe's
    feedback summary for the household (last_verdict, last_made_on, counts per verdict, total)."""
    return await run_in_context(
        record_recipe_feedback_impl,
        recipe=recipe,
        verdict=verdict,
        effort=effort,
        note=note,
        for_whom=for_whom,
        made_on=made_on,
    )


@mcp_server.tool()
@require_scope("recipes:read")
async def get_recipe_feedback(recipe: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Read this household's recipe feedback, newest first (by made_on): one recipe's entries when
    `recipe` (slug or id) is given, otherwise the latest entries across all recipes. `limit` is
    1..50 (default 10). Returns {items: [{id, recipe: {id, slug, name}, verdict, effort, note,
    for_whom, made_on, recorded_by}], total}; dates are ISO YYYY-MM-DD. Do not propose a
    `never_again` recipe unless the user asks for it; prefer `loved` ones when the user wants
    something reliable."""
    return await run_in_context(get_recipe_feedback_impl, recipe=recipe, limit=limit)
