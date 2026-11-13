"""What the TRMNL "Ce soir" screen shows: the next planned meal and what is missing for it.

Read-only. Mealie does the matching; the TRMNL template only draws what this returns
(spec: docs/superpowers/specs/2026-11-11-trmnl-tonight-design.md).
"""

from datetime import date, datetime, time, timedelta

from mealie.core.config import get_app_settings
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.household.cooked_meal import UnmatchedIngredient
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.household.pantry import PantryItemOut, PantryLocation
from mealie.schema.household.trmnl import (
    TrmnlAtHome,
    TrmnlPlace,
    TrmnlRecipe,
    TrmnlState,
    TrmnlToBuy,
    TrmnlTonightOut,
    TrmnlUseSoon,
)
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import IngredientFood, RecipeIngredient
from mealie.schema.response.pagination import PaginationQuery
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.claude_context.cooked_meal_service import CookedMealService
from mealie.services.claude_context.freshness import NEEDS_ATTENTION, freshness_of
from mealie.services.claude_context.pantry_usage import uncovered_fraction
from mealie.services.claude_context.trmnl_format import (
    PLACE_NAMES,
    clock,
    facts_line,
    kicker,
    quantity_text,
    use_soon_text,
)

MEAL_ORDER = (
    PlanEntryType.breakfast,
    PlanEntryType.lunch,
    PlanEntryType.snack,
    PlanEntryType.dinner,
    PlanEntryType.side,
)
"""The order meals come in a day; a side goes with dinner, after it. Drinks and desserts are never shown."""

MEAL_ENDS = {
    PlanEntryType.breakfast: 10,
    PlanEntryType.lunch: 14,
    PlanEntryType.snack: 17,
    PlanEntryType.dinner: 21,
    PlanEntryType.side: 21,
}
"""Hour from which today's meal of that type is over, ticked or not, and the screen moves on."""

LOOK_AHEAD_DAYS = 7

USE_SOON_ROWS = 8
PLACE_ITEMS = 30
PLACE_ORDER = (PantryLocation.fridge, PantryLocation.freezer, PantryLocation.cupboard, PantryLocation.other)

TO_BUY_ROWS = 8
"""Rows that fit in the "À acheter" column; past that, the last row becomes "+ N autres"."""


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
        entry = self._pick(today, now)
        if entry is None:
            pantry = self.repos.pantry_items.ordered()
            return TrmnlTonightOut(
                state=TrmnlState.nothing_planned,
                kicker=kicker(today, today),
                generated_at=clock(now),
                use_soon=self._use_soon(today, pantry),
                places=self._places(pantry),
            )
        base = {"kicker": kicker(entry.date, today, entry.entry_type), "generated_at": clock(now)}

        recipe = self._recipe(entry)
        if recipe is None:
            return TrmnlTonightOut(
                state=TrmnlState.no_recipe, recipe=TrmnlRecipe(name=entry.title or entry.text, facts=""), **base
            )

        return TrmnlTonightOut(
            state=TrmnlState.planned,
            recipe=self._recipe_out(recipe, entry),
            **self._ingredients(recipe, entry, today),
            **base,
        )

    # ------------------------------------------------------------------ picking the next meal

    def _pick(self, today: date, now: datetime) -> ReadPlanEntry | None:
        """The next meal still to come within `LOOK_AHEAD_DAYS`: by day, then `MEAL_ORDER`; an entry with a recipe
        before a free-text one, then the lowest id. Cooked entries are done, and so is today's meal once its hour in
        `MEAL_ENDS` has passed, so a lunch nobody ticked doesn't stay on the screen all evening."""
        start = datetime.combine(today, time())
        end = datetime.combine(today + timedelta(days=LOOK_AHEAD_DAYS - 1), time())
        candidates = [
            e
            for e in self.repos.meals.get_meals_by_date_range(start, end)
            if e.entry_type in MEAL_ORDER
            and e.cooked_at is None
            and today <= e.date < today + timedelta(days=LOOK_AHEAD_DAYS)
            and not (e.date == today and now.hour >= MEAL_ENDS[e.entry_type])
        ]
        candidates.sort(key=lambda e: (e.date, MEAL_ORDER.index(e.entry_type), e.recipe_id is None, e.id))
        return candidates[0] if candidates else None

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

    @staticmethod
    def _use_soon(today: date, pantry: list[PantryItemOut]) -> list[TrmnlUseSoon]:
        """Pantry items needing attention, worst first, pantry order kept within a status."""
        rows = []
        for index, item in enumerate(pantry):
            f = freshness_of(item, today)
            if f.status in NEEDS_ATTENTION:
                use_soon = TrmnlUseSoon(name=item.name, when=use_soon_text(f), place=PLACE_NAMES[item.location])
                rows.append((NEEDS_ATTENTION.index(f.status), index, use_soon))
        rows.sort(key=lambda row: (row[0], row[1]))
        return [row[2] for row in rows[:USE_SOON_ROWS]]

    @staticmethod
    def _places(pantry: list[PantryItemOut]) -> list[TrmnlPlace]:
        """The pantry by place, in `PLACE_ORDER`, keeping the pantry's soonest-first order; empty places left out."""
        places = []
        for location in PLACE_ORDER:
            names = [item.name for item in pantry if item.location == location]
            if names:
                places.append(TrmnlPlace(name=PLACE_NAMES[location], count=len(names), items=names[:PLACE_ITEMS]))
        return places

    # ------------------------------------------------------------------ what to buy, what is at home

    def _ingredients(self, recipe: Recipe, entry: ReadPlanEntry, today: date) -> dict:
        """`to_buy`, `to_buy_more`, `at_home`, `ingredient_count` and `to_check_count` for a planned recipe.

        Uses the recipe page's pantry check, so both always agree, plus whether the pantry holds enough. Anything
        that can't be judged (a line without a food, units that don't compare, a missing quantity) counts in
        `to_check_count`, so the screen never says "Rien à acheter" on a guess.
        """
        assert recipe.id is not None
        scale = entry.recipe_scale
        check = CookedMealService(self.repos, self.user, self.household).pantry_check(recipe.id, today, scale=scale)
        pantry = self.repos.pantry_items.ordered()
        pantry_by_id = {str(item.id): item for item in pantry}
        items_by_ref = {str(m.reference_id): m.pantry_item_ids for m in check.ingredients}
        unmatched = {str(u.food.id): u for u in check.unmatched_ingredients}
        on_list = self._foods_on_list()

        to_check = 0
        lines_by_food: dict[str, list[RecipeIngredient]] = {}
        for line in recipe.recipe_ingredient:
            if line.food is None:
                if (line.note or line.original_text or line.display or "").strip():
                    to_check += 1
                continue
            lines_by_food.setdefault(str(line.food.id), []).append(line)

        to_buy: list[TrmnlToBuy] = []
        at_home: list[TrmnlAtHome] = []
        for food_id, lines in lines_by_food.items():
            food = lines[0].food
            assert food is not None
            items = [
                pantry_by_id[str(item_id)]
                for item_id in items_by_ref.get(str(lines[0].reference_id), [])
                if str(item_id) in pantry_by_id
            ]
            if items:
                uncovered = uncovered_fraction(lines, items, scale)
                if uncovered is None:
                    to_check += 1
                if not uncovered:  # 0.0 covered, None can't tell: at home either way
                    at_home.append(TrmnlAtHome(name=food.name, use_soon=self._use_soon_any(items, today)))
                    continue
                to_buy.append(self._to_buy(food, lines, scale, on_list, left=self._left(items)))
                continue

            substitutes = self._substitutes(unmatched.get(food_id), pantry)
            uncovered = uncovered_fraction(lines, substitutes, scale) if substitutes else 1.0
            if not uncovered:  # the substitute is enough (0.0), or can't tell (None)
                if uncovered is None:
                    to_check += 1
                first = substitutes[0]
                name = first.food.name if first.food else first.name
                at_home.append(
                    TrmnlAtHome(name=f"{name} (pour {food.name})", use_soon=self._use_soon_any(substitutes, today))
                )
                continue
            to_buy.append(self._to_buy(food, lines, scale, on_list))

        more = 0
        if len(to_buy) > TO_BUY_ROWS:
            more = len(to_buy) - (TO_BUY_ROWS - 1)
            to_buy = to_buy[: TO_BUY_ROWS - 1]
        return {
            "to_buy": to_buy,
            "to_buy_more": more,
            "at_home": at_home,
            "ingredient_count": len(lines_by_food),
            # a recipe without any ingredient line can't be judged: never "Rien à acheter" for it
            "to_check_count": to_check if recipe.recipe_ingredient else 1,
        }

    def _foods_on_list(self) -> set[str]:
        """Foods on an unchecked item of any of the household's shopping lists."""
        items = self.repos.group_shopping_list_item.page_all(
            PaginationQuery(page=1, per_page=-1, query_filter="checked = false AND foodId IS NOT NULL")
        ).items
        return {str(item.food_id) for item in items if item.food_id}

    @staticmethod
    def _substitutes(unmatched: UnmatchedIngredient | None, pantry: list[PantryItemOut]) -> list[PantryItemOut]:
        """Pantry items of the first substitute food the pantry holds, in the order the food offers them."""
        if unmatched is None:
            return []
        for substitute_id in unmatched.substitute_food_ids:
            items = [item for item in pantry if item.food_id is not None and str(item.food_id) == str(substitute_id)]
            if items:
                return items
        return []

    @staticmethod
    def _use_soon_any(items: list[PantryItemOut], today: date) -> bool:
        return any(freshness_of(item, today).status in NEEDS_ATTENTION for item in items)

    @staticmethod
    def _to_buy(
        food: IngredientFood, lines: list[RecipeIngredient], scale: float, on_list: set[str], left: str | None = None
    ) -> TrmnlToBuy:
        """The recipe's quantity of the food, scaled: summed over its lines when they share a unit, else the first."""
        first = lines[0]
        same_unit = all(
            (line.unit.id if line.unit else None) == (first.unit.id if first.unit else None) for line in lines
        )
        amounts = lines if same_unit else [first]
        quantity = sum(line.quantity or 0 for line in amounts) * scale
        return TrmnlToBuy(
            name=food.name,
            quantity=quantity_text(quantity, first.unit),
            left=left,
            on_list=str(food.id) in on_list,
        )

    @staticmethod
    def _left(items: list[PantryItemOut]) -> str | None:
        """What the pantry still holds, when its items share a unit: "reste 100 ml"."""
        unit_ids = {str(item.unit_id) for item in items}
        if len(unit_ids) != 1:
            return None
        text = quantity_text(sum(item.quantity or 0 for item in items), items[0].unit)
        return f"reste {text}" if text else None
