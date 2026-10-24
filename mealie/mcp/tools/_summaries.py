from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from pydantic import UUID4
from sqlalchemy.orm import Session

from mealie.core.config import get_app_settings
from mealie.db.models.household.household_to_recipe import HouseholdToRecipe
from mealie.mcp.context import McpContext
from mealie.schema.household.recipe_feedback import RecipeFeedbackOut, RecipeFeedbackSummary
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.services.claude_context.recipe_feedback_service import RecipeFeedbackService

DESCRIPTION_MAX = 200


def recipe_url(group_slug: str, slug: str) -> str:
    return f"{get_app_settings().BASE_URL.rstrip('/')}/g/{group_slug}/r/{slug}"


def last_made_by_recipe(session: Session, household_id: UUID4, recipe_ids: Iterable[UUID4]) -> dict[UUID4, date]:
    """`last_made` (as a date) for the given recipes in one household, in a single query."""
    ids = list(recipe_ids)
    if not ids:
        return {}
    stmt = sa.select(HouseholdToRecipe.recipe_id, HouseholdToRecipe.last_made).where(
        HouseholdToRecipe.household_id == household_id,
        HouseholdToRecipe.recipe_id.in_(ids),
        HouseholdToRecipe.last_made.is_not(None),
    )
    return {recipe_id: last_made.date() for recipe_id, last_made in session.execute(stmt).all()}


def _truncate(text: str | None, limit: int = DESCRIPTION_MAX) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return (value.date() if isinstance(value, datetime) else value).isoformat()


def feedback_service(ctx: McpContext) -> RecipeFeedbackService:
    """The feedback service on the caller's household-scoped repositories."""
    return RecipeFeedbackService(ctx.repos, ctx.user)


def feedback_summaries(ctx: McpContext, recipe_ids: Iterable[UUID4 | None]) -> dict[UUID4, RecipeFeedbackSummary]:
    """The household's feedback summaries for the given recipes, in one batched lookup."""
    ids = list(dict.fromkeys(i for i in recipe_ids if i is not None))
    return feedback_service(ctx).summaries(ids) if ids else {}


def last_verdict(summaries: dict[UUID4, RecipeFeedbackSummary], recipe_id: UUID4 | None) -> str | None:
    summary = summaries.get(recipe_id) if recipe_id else None
    return summary.last_verdict.value if summary else None


def summary_dict(summary: RecipeFeedbackSummary | None) -> dict[str, Any] | None:
    return summary.model_dump(mode="json") if summary else None


def feedback_dict(row: RecipeFeedbackOut) -> dict[str, Any]:
    """Compact, JSON-serialisable view of a feedback row."""
    return {
        "id": str(row.id),
        "recipe": {"id": str(row.recipe.id), "slug": row.recipe.slug, "name": row.recipe.name},
        "verdict": row.verdict.value,
        "effort": row.effort,
        "note": row.note,
        "for_whom": row.for_whom,
        "made_on": row.made_on.isoformat(),
        "recorded_by": row.user_name,
    }


def recipe_brief(
    r: RecipeSummary, last_made: date | None, group_slug: str, last_verdict: str | None = None
) -> dict[str, Any]:
    """Compact, JSON-serialisable view of a recipe for search results; `last_verdict` is the household's latest
    feedback verdict (null when it has none)."""
    return {
        "id": str(r.id) if r.id else None,
        "slug": r.slug,
        "name": r.name,
        "description": _truncate(r.description),
        "total_time": r.total_time,
        "prep_time": r.prep_time,
        "servings": r.recipe_servings or None,
        "rating": r.rating,
        "tags": [t.name for t in r.tags or []],
        "categories": [c.name for c in r.recipe_category or []],
        "last_made": _iso(last_made),
        "last_verdict": last_verdict,
        "url": recipe_url(group_slug, r.slug),
    }
