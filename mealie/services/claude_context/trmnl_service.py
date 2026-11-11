"""What the TRMNL "Ce soir" screen shows: tonight's planned meal and what is missing for it.

Read-only. Mealie does the matching; the TRMNL template only draws what this returns
(spec: docs/superpowers/specs/2026-11-11-trmnl-tonight-design.md).
"""

from datetime import date, datetime, time

from mealie.core.config import get_app_settings
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.household.trmnl import TrmnlRecipe, TrmnlState, TrmnlTonightOut, TrmnlUseSoon
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.claude_context.freshness import NEEDS_ATTENTION, freshness_of
from mealie.services.claude_context.trmnl_format import clock, facts_line, kicker, use_soon_text

MEAL_ORDER = (
    PlanEntryType.dinner,
    PlanEntryType.side,
    PlanEntryType.lunch,
    PlanEntryType.snack,
    PlanEntryType.breakfast,
)
"""Which entry is "ce soir", most likely first; drinks and desserts are never it."""

USE_SOON_ROWS = 6


class TrmnlTonightService(BaseService):
    def __init__(self, repos: AllRepositories, user: PrivateUser, household: HouseholdInDB):
        if str(repos.pantry_items.household_id) != str(user.household_id) or str(household.id) != str(
            user.household_id
        ):
            raise ValueError("TrmnlTonightService needs repositories scoped to the user's household.")
        self.repos = repos
        self.user = user
        self.household = household
        super().__init__()

    def tonight(self, today: date | None = None, now: datetime | None = None) -> TrmnlTonightOut:
        now = now or datetime.now().astimezone()
        today = today or now.date()
        base = {"kicker": kicker(today), "generated_at": clock(now)}

        entry = self._pick(today)
        if entry is None:
            return TrmnlTonightOut(state=TrmnlState.nothing_planned, use_soon=self._use_soon(today), **base)

        recipe = self._recipe(entry)
        if recipe is None:
            return TrmnlTonightOut(
                state=TrmnlState.no_recipe, recipe=TrmnlRecipe(name=entry.title or entry.text, facts=""), **base
            )

        return TrmnlTonightOut(state=TrmnlState.planned, recipe=self._recipe_out(recipe, entry), **base)

    # ------------------------------------------------------------------ picking tonight

    def _pick(self, today: date) -> ReadPlanEntry | None:
        """By meal type (`MEAL_ORDER`), then an entry with a recipe before a free-text one, then the lowest id."""
        day = datetime.combine(today, time())
        entries = [
            entry
            for entry in self.repos.meals.get_meals_by_date_range(day, day)
            if entry.cooked_at is None and entry.entry_type in MEAL_ORDER
        ]
        entries.sort(key=lambda e: (MEAL_ORDER.index(e.entry_type), e.recipe_id is None, e.id))
        return entries[0] if entries else None

    def _recipe(self, entry: ReadPlanEntry) -> Recipe | None:
        if entry.recipe_id is None:
            return None
        # recipes are shared across the group's households
        group_recipes = get_repositories(self.repos.session, group_id=self.user.group_id, household_id=None).recipes
        return group_recipes.get_one(entry.recipe_id, "id")

    def _recipe_out(self, recipe: Recipe, entry: ReadPlanEntry) -> TrmnlRecipe:
        assert recipe.id is not None
        summary = self.repos.recipe_feedback.summaries([recipe.id]).get(recipe.id)
        servings = recipe.recipe_servings * entry.recipe_scale if recipe.recipe_servings else None
        image_url = (
            f"{get_app_settings().BASE_URL}/api/media/recipes/{recipe.id}/images/min-original.webp"
            if recipe.image
            else None
        )
        return TrmnlRecipe(
            name=recipe.name or "",
            facts=facts_line(recipe.total_time_seconds, servings, summary.last_verdict if summary else None),
            image_url=image_url,
        )

    def _use_soon(self, today: date) -> list[TrmnlUseSoon]:
        """Pantry items needing attention, worst first, pantry order kept within a status."""
        rows = []
        for index, item in enumerate(self.repos.pantry_items.ordered()):
            f = freshness_of(item, today)
            if f.status in NEEDS_ATTENTION:
                rows.append(
                    (NEEDS_ATTENTION.index(f.status), index, TrmnlUseSoon(name=item.name, when=use_soon_text(f)))
                )
        rows.sort(key=lambda row: (row[0], row[1]))
        return [row[2] for row in rows[:USE_SOON_ROWS]]
