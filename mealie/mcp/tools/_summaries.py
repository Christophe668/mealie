from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from pydantic import UUID4
from sqlalchemy.orm import Session

from mealie.core.config import get_app_settings
from mealie.db.models.household.household_to_recipe import HouseholdToRecipe
from mealie.schema.recipe.recipe import RecipeSummary

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


def recipe_brief(r: RecipeSummary, last_made: date | None, group_slug: str) -> dict[str, Any]:
    """Compact, JSON-serialisable view of a recipe for search results."""
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
        "url": recipe_url(group_slug, r.slug),
    }
