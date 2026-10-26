import math
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from mealie.core.exceptions import NoEntryFound
from mealie.db.models.recipe import IngredientFoodModel
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.repos.single_commit import single_commit
from mealie.schema.household.cooked_meal import (
    CookedLeftovers,
    CookedMealCreate,
    CookedMealOut,
    PantryCheckOut,
    PantryOutcome,
)
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.household.pantry import (
    PantryItemCreate,
    PantryItemOut,
    PantryItemUpdate,
    PantryLocation,
    PantrySource,
)
from mealie.schema.household.recipe_feedback import RecipeFeedbackCreate, RecipeFeedbackOut
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.claude_context.pantry_service import PantryService
from mealie.services.claude_context.recipe_feedback_service import (
    FutureMadeOnError,
    RecipeFeedbackService,
    local_noon,
    move_last_made_forward,
)
from mealie.services.claude_context.recipe_writer import food_name_variants

LEFTOVER_USE_BY_DAYS: dict[str, int] = {"fridge": 3, "freezer": 90}
LEFTOVER_PORTIONS_MIN, LEFTOVER_PORTIONS_MAX = 1, 50


class AlreadyCookedError(ValueError):
    """An entry with this recipe is already marked cooked on the cooking date (or the given entry is done)."""

    def __init__(self, cooked_on: date):
        self.cooked_on = cooked_on
        super().__init__(f"already recorded as cooked on {cooked_on.isoformat()}")


class PantryItemNotInRecipeError(ValueError):
    """Pantry outcomes were given for items that don't match the recipe (or were listed twice)."""

    def __init__(self, item_ids: list[str], reason: str = "pantry items not in this recipe"):
        self.item_ids = item_ids
        super().__init__(f"{reason}: {', '.join(item_ids)}")


def _local_day(moment: datetime) -> date:
    """The server-local date of a stored timestamp (stored as naive UTC)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone().date()


class CookedMealService(BaseService):
    """Recording a cooked meal (spec § 4): meal plan entry done, last made, pantry outcomes, leftovers, feedback.

    `record` checks everything before the first write and then writes inside one transaction (`single_commit`):
    a refused or failed call keeps nothing.
    """

    def __init__(self, repos: AllRepositories, user: PrivateUser, household: HouseholdInDB):
        scope = repos.pantry_items
        if str(scope.household_id) != str(user.household_id) or str(household.id) != str(user.household_id):
            raise ValueError("CookedMealService needs repositories scoped to the user's household.")
        self.repos = repos
        self.user = user
        self.household = household
        super().__init__()

    # ------------------------------------------------------------------ reads

    def _get_recipe_or_raise(self, recipe_id: UUID) -> Recipe:
        # recipes are shared across the group's households: look up group-wide, as the feedback service does
        group_recipes = get_repositories(self.repos.session, group_id=self.user.group_id, household_id=None).recipes
        recipe = group_recipes.get_one(recipe_id, "id")
        if recipe is None:
            raise NoEntryFound("Recipe not found.")
        return recipe

    def _matching_items(self, recipe: Recipe, pantry: list[PantryItemOut] | None = None) -> list[PantryItemOut]:
        """Pantry items matching the recipe's foods: by `food_id`, or (items without a food) by the food's name or
        its simple singular/plural, case-insensitively. In `get_pantry` order."""
        food_ids: set[str] = set()
        names: set[str] = set()
        for ingredient in recipe.recipe_ingredient:
            if ingredient.food is None:
                continue
            food_ids.add(str(ingredient.food.id))
            key = IngredientFoodModel.normalize(ingredient.food.name)
            names.add(key)
            names.update(food_name_variants(key))

        def matches(item: PantryItemOut) -> bool:
            if item.food_id is not None:
                return str(item.food_id) in food_ids
            return IngredientFoodModel.normalize(item.name) in names

        items = self.repos.pantry_items.ordered() if pantry is None else pantry
        return [item for item in items if matches(item)]

    def _suggested_portions(self, recipe: Recipe, scale: float) -> int:
        """Servings cooked minus the household's `default_servings`, when both are known and positive; else 0."""
        preferences = self.repos.meal_preferences.get_for_household()
        default_servings = preferences.default_servings if preferences else None
        if not recipe.recipe_servings or not default_servings:
            return 0
        return max(math.floor(recipe.recipe_servings * scale - default_servings), 0)

    def find_entry(self, recipe_id: UUID, cooked_on: date) -> ReadPlanEntry | None:
        """The not-yet-done entry of the household for this recipe dated the cooking date or the day before;
        the closest date wins, then the lowest id."""
        start = datetime.combine(cooked_on - timedelta(days=1), time())
        end = datetime.combine(cooked_on, time())
        candidates = [
            entry
            for entry in self.repos.meals.get_meals_by_date_range(start, end)
            if entry.recipe_id is not None and str(entry.recipe_id) == str(recipe_id) and entry.cooked_at is None
        ]
        candidates.sort(key=lambda entry: (abs((cooked_on - entry.date).days), entry.id))
        return candidates[0] if candidates else None

    def pantry_check(self, recipe_id: UUID, cooked_on: date, scale: float | None = None) -> PantryCheckOut:
        """The pantry items matching the recipe, the suggested leftover portions and the entry a cooking would mark.

        The scale is the given one, else the matching entry's `recipe_scale`, else 1.
        """
        recipe = self._get_recipe_or_raise(recipe_id)
        entry = self.find_entry(recipe_id, cooked_on)
        if scale is None:
            scale = entry.recipe_scale if entry else 1.0
        return PantryCheckOut(
            items=self._matching_items(recipe),
            suggested_leftover_portions=self._suggested_portions(recipe, scale),
            meal_plan_entry_id=entry.id if entry else None,
        )

    # ------------------------------------------------------------------ writes

    def record(self, data: CookedMealCreate, today: date | None = None, *, amend: bool = False) -> CookedMealOut:
        """Record a cooking, all or nothing.

        With `amend`, a cooking already recorded (that day, or on the given entry) is not refused: what comes with
        it (pantry outcomes, leftovers, feedback) is added and no entry is marked. This is "How was it?" told later,
        after the meal was ticked done or cook mode was skipped.

        Raises, writing nothing: `FutureMadeOnError` (cooked_on later than the server's tomorrow), `NoEntryFound`
        (recipe outside the group, entry or pantry item outside the household, or an entry for another recipe),
        `AlreadyCookedError` (without `amend`), `PantryItemNotInRecipeError` (items not matching the recipe, or
        listed twice) and `ValueError` (leftover portions or location out of range).
        """
        today = today or datetime.now().astimezone().date()
        latest = today + timedelta(days=1)
        if data.cooked_on > latest:
            raise FutureMadeOnError(
                f"cooked_on cannot be later than {latest.isoformat()}, got {data.cooked_on.isoformat()}."
            )
        recipe = self._get_recipe_or_raise(data.recipe_id)
        already_cooked = self._cooked_on(data.recipe_id, data.cooked_on)
        if already_cooked and not amend:
            raise AlreadyCookedError(data.cooked_on)
        entry = None if already_cooked else self._entry_to_mark(data.recipe_id, data, amend=amend)
        outcomes = self._checked_outcomes(recipe, data)
        if data.leftovers is not None:
            self._check_leftovers(data.leftovers)

        pantry = PantryService(self.repos)
        with single_commit(self.repos.session):
            feedback: RecipeFeedbackOut | None = None
            if data.feedback is not None:
                # also moves last made forward
                feedback = RecipeFeedbackService(self.repos, self.user).record(
                    RecipeFeedbackCreate(
                        recipe_id=recipe.id,
                        verdict=data.feedback.verdict,
                        effort=data.feedback.effort,
                        made_on=data.cooked_on,
                    ),
                    today=today,
                )
            else:
                move_last_made_forward(self.repos, self.user, recipe, local_noon(data.cooked_on))

            # local noon of the cooking date (not "now"), so a back-dated repeat is still caught as already recorded
            cooked_at = local_noon(data.cooked_on)
            marked = self.repos.meals.patch(entry.id, {"cooked_at": cooked_at}) if entry else None

            removed_ids: list[UUID] = []
            kept: list[PantryItemOut] = []
            for item, outcome in outcomes:
                if outcome == PantryOutcome.used_up:
                    removed_ids.append(pantry.remove_item(item.id).id)
                elif item.opened_on is None:
                    update = PantryItemUpdate(**item.model_dump(include=set(PantryItemUpdate.model_fields)))
                    update.opened_on = data.cooked_on
                    kept.append(pantry.update_item(item.id, update))
                else:
                    kept.append(item)

            leftover = (
                self._add_leftover(recipe, data.cooked_on, data.leftovers) if data.leftovers is not None else None
            )

        return CookedMealOut(
            meal_plan_entry=marked,
            removed_item_ids=removed_ids,
            kept_items=kept,
            leftover=leftover,
            feedback=feedback,
        )

    def mark_entry(self, entry_id: int, cooked_on: date) -> CookedMealOut:
        """Tick a meal plan entry done. A recipe entry is recorded as a cooking (no pantry outcomes, leftovers or
        feedback); a title-only entry just gets `cooked_at` (no last made). `NoEntryFound` outside the household,
        `AlreadyCookedError` when it is done already."""
        entry = self.repos.meals.get_one(entry_id)  # household-scoped
        if entry is None:
            raise NoEntryFound("Meal plan entry not found.")
        if entry.recipe_id is not None:
            return self.record(
                CookedMealCreate(recipe_id=entry.recipe_id, meal_plan_entry_id=entry.id, cooked_on=cooked_on)
            )
        if entry.cooked_at is not None:
            raise AlreadyCookedError(_local_day(entry.cooked_at))
        return CookedMealOut(meal_plan_entry=self.repos.meals.patch(entry.id, {"cooked_at": local_noon(cooked_on)}))

    def uncook_entry(self, entry_id: int) -> ReadPlanEntry:
        """Clear an entry's done state; last made is left as it is. `NoEntryFound` outside the household."""
        entry = self.repos.meals.get_one(entry_id)
        if entry is None:
            raise NoEntryFound("Meal plan entry not found.")
        return self.repos.meals.patch(entry.id, {"cooked_at": None})

    # ------------------------------------------------------------------ helpers

    def _cooked_on(self, recipe_id: UUID, cooked_on: date) -> bool:
        start = datetime.combine(cooked_on, time()).astimezone()
        end = datetime.combine(cooked_on + timedelta(days=1), time()).astimezone()
        return bool(self.repos.meals.cooked_between(recipe_id, start, end))

    def _entry_to_mark(self, recipe_id: UUID, data: CookedMealCreate, *, amend: bool = False) -> ReadPlanEntry | None:
        if data.meal_plan_entry_id is None:
            return self.find_entry(recipe_id, data.cooked_on)
        entry = self.repos.meals.get_one(data.meal_plan_entry_id)  # household-scoped
        if entry is None or entry.recipe_id is None or str(entry.recipe_id) != str(recipe_id):
            raise NoEntryFound("Meal plan entry not found for this recipe.")
        if entry.cooked_at is not None:
            if amend:
                return None
            raise AlreadyCookedError(_local_day(entry.cooked_at))
        return entry

    def _checked_outcomes(self, recipe: Recipe, data: CookedMealCreate) -> list[tuple[PantryItemOut, PantryOutcome]]:
        ids = [str(outcome.pantry_item_id) for outcome in data.pantry]
        repeated = sorted(item_id for item_id, count in Counter(ids).items() if count > 1)
        if repeated:
            raise PantryItemNotInRecipeError(repeated, reason="pantry items listed more than once")

        pantry = self.repos.pantry_items.ordered()  # household-scoped
        in_household = {str(item.id) for item in pantry}
        missing = [item_id for item_id in ids if item_id not in in_household]
        if missing:
            raise NoEntryFound(f"pantry items not found: {', '.join(missing)}")

        matched = {str(item.id): item for item in self._matching_items(recipe, pantry)}
        not_in_recipe = [item_id for item_id in ids if item_id not in matched]
        if not_in_recipe:
            raise PantryItemNotInRecipeError(not_in_recipe)
        return [(matched[str(outcome.pantry_item_id)], outcome.outcome) for outcome in data.pantry]

    @staticmethod
    def _check_leftovers(leftovers: CookedLeftovers) -> None:
        # the schema enforces these too; checked again for callers that build the model without validation
        if not LEFTOVER_PORTIONS_MIN <= leftovers.portions <= LEFTOVER_PORTIONS_MAX:
            raise ValueError(f"leftover portions must be {LEFTOVER_PORTIONS_MIN}-{LEFTOVER_PORTIONS_MAX}")
        if leftovers.location not in LEFTOVER_USE_BY_DAYS:
            raise ValueError("leftover location must be fridge or freezer")

    def _add_leftover(self, recipe: Recipe, cooked_on: date, leftovers: CookedLeftovers) -> PantryItemOut:
        """One new pantry row per cooking (never merged into an earlier leftover of the same recipe)."""
        use_by = leftovers.use_by or cooked_on + timedelta(days=LEFTOVER_USE_BY_DAYS[leftovers.location])
        return self.repos.pantry_items.create(
            PantryItemCreate(
                name=f"Leftover {recipe.name}",
                quantity=leftovers.portions,
                location=PantryLocation(leftovers.location),
                bought_on=cooked_on,
                use_by=use_by,
                source=PantrySource.leftover,
                note="portions",
            )
        )
