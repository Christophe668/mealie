from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import UUID4, Field

from mealie.schema._mealie import MealieModel
from mealie.schema.household.pantry import PantryItemOut
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackOut
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.recipe.recipe_ingredient import IngredientFood


class PantryOutcome(StrEnum):
    used_up = "used_up"
    some_left = "some_left"


class ProposedOutcome(StrEnum):
    used_up = "used_up"
    some_left = "some_left"
    none = "none"
    """The recipe takes nothing from this pantry item (an earlier item of the same food covered it)."""


class ProposalReason(StrEnum):
    subtracted = "subtracted"
    """Same unit on both sides: the recipe's amount was taken off."""
    converted = "converted"
    """Different but compatible units, converted into the pantry item's unit."""
    weight_from_note = "weight_from_note"
    """Pieces turned into weight with a `200 g` found in the ingredient's note."""
    weight_from_food = "weight_from_food"
    """Pieces and weight turned into each other with the food's `grams_each`."""
    units_differ = "units_differ"
    """No way to compare the recipe's unit with the pantry item's: nothing is subtracted."""
    small_amount = "small_amount"
    """The recipe takes under 5% of the item, so the quantity is left alone."""
    no_quantity = "no_quantity"
    """The recipe or the pantry item has no quantity to work with."""


class PantryProposal(MealieModel):
    pantry_item_id: UUID4
    used: float | None = None
    """What the recipe takes, in the pantry item's unit; `None` when it can't be worked out."""
    proposed_quantity: float | None = None
    """The quantity left to suggest; `None` only when the pantry item has no quantity."""
    proposed_outcome: ProposedOutcome
    reason: ProposalReason | None = None
    """`None` only with the outcome `none`."""
    replaces_reference_id: UUID4 | None = None
    """Set when the item stands in for this recipe ingredient (a substitute), not the ingredient's own food."""


class CookedPantryOutcome(MealieModel):
    pantry_item_id: UUID4
    outcome: PantryOutcome
    quantity: Annotated[float | None, Field(ge=0)] = None
    """The quantity left, for `some_left` only; `None` keeps the item's current one."""
    replaces_reference_id: UUID4 | None = None
    """Set when the item stands in for this recipe ingredient (a substitute), not the ingredient's own food."""


class CookedLeftovers(MealieModel):
    portions: Annotated[int, Field(ge=1, le=50)]
    location: Literal["fridge", "freezer"] = "fridge"
    use_by: date | None = None
    """`None` means the cooking date + 3 days (fridge) or + 90 days (freezer)."""


class CookedFeedback(MealieModel):
    verdict: FeedbackVerdict
    effort: Annotated[int | None, Field(ge=1, le=3)] = None
    """1 easy, 2 fine, 3 a lot of work (as `RecipeFeedbackCreate.effort`)."""


class CookedMealCreate(MealieModel):
    recipe_id: UUID4
    cooked_on: date
    """The cook's own day (their local date), never the server's."""
    meal_plan_entry_id: int | None = None
    """`None` means the matching not-yet-done entry of the household, if any."""
    scale: Annotated[float | None, Field(gt=0)] = None
    pantry: list[CookedPantryOutcome] = []
    leftovers: CookedLeftovers | None = None
    feedback: CookedFeedback | None = None


class CookedMealOut(MealieModel):
    meal_plan_entry: ReadPlanEntry | None = None
    """The entry marked done, or `None` when none was found."""
    removed_item_ids: list[UUID4] = []
    kept_items: list[PantryItemOut] = []
    leftover: PantryItemOut | None = None
    feedback: RecipeFeedbackOut | None = None


class PantryIngredientMatch(MealieModel):
    reference_id: UUID4
    """The recipe ingredient's `reference_id`."""
    pantry_item_ids: list[UUID4] = []
    """Its pantry items, in pantry order; empty when the pantry has none of its food."""


class UnmatchedIngredient(MealieModel):
    reference_id: UUID4
    """The recipe ingredient's `reference_id`."""
    food: IngredientFood
    substitute_food_ids: list[UUID4] = []
    """The foods the ingredient's food may be replaced by, in the order to offer them."""


class PantryCheckOut(MealieModel):
    items: list[PantryItemOut]
    suggested_leftover_portions: int
    meal_plan_entry_id: int | None = None
    ingredients: list[PantryIngredientMatch] = []
    """One per ingredient that names a food; an ingredient without one can't be matched, so it is left out."""
    proposals: list[PantryProposal] = []
    """One per item in `items`, in the same order."""
    unmatched_ingredients: list[UnmatchedIngredient] = []
    """Ingredients naming a food that no pantry item matches and no substitute stands in for."""
