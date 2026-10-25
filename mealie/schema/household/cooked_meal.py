from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import UUID4, Field

from mealie.schema._mealie import MealieModel
from mealie.schema.household.pantry import PantryItemOut
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackOut
from mealie.schema.meal_plan.new_meal import ReadPlanEntry


class PantryOutcome(StrEnum):
    used_up = "used_up"
    some_left = "some_left"


class CookedPantryOutcome(MealieModel):
    pantry_item_id: UUID4
    outcome: PantryOutcome


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


class PantryCheckOut(MealieModel):
    items: list[PantryItemOut]
    suggested_leftover_portions: int
    meal_plan_entry_id: int | None = None
