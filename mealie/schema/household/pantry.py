from datetime import date, datetime
from enum import StrEnum

from pydantic import UUID4, ConfigDict
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household.pantry import PantryItem
from mealie.db.models.recipe import IngredientFoodModel, IngredientFoodSubstitutionModel, IngredientUnitModel
from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientUnit
from mealie.schema.response.pagination import PaginationBase


class PantryLocation(StrEnum):
    fridge = "fridge"
    freezer = "freezer"
    cupboard = "cupboard"
    other = "other"


class PantrySource(StrEnum):
    shopping = "shopping"
    manual = "manual"
    leftover = "leftover"


class PantryItemCreate(MealieModel):
    name: str
    food_id: UUID4 | None = None
    quantity: float | None = None
    unit_id: UUID4 | None = None
    location: PantryLocation = PantryLocation.cupboard
    bought_on: date | None = None
    opened_on: date | None = None
    use_by: date | None = None
    source: PantrySource = PantrySource.manual
    note: str | None = None


class PantryItemUpdate(PantryItemCreate):
    pass


class PantryItemOut(PantryItemCreate):
    id: UUID4
    group_id: UUID4
    household_id: UUID4

    food: IngredientFood | None = None
    unit: IngredientUnit | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            selectinload(PantryItem.food).selectinload(IngredientFoodModel.households_with_ingredient_food),
            selectinload(PantryItem.food).selectinload(IngredientFoodModel.aliases),
            selectinload(PantryItem.food).joinedload(IngredientFoodModel.extras),
            selectinload(PantryItem.food).joinedload(IngredientFoodModel.label),
            selectinload(PantryItem.food)
            .selectinload(IngredientFoodModel.substitutions)
            .joinedload(IngredientFoodSubstitutionModel.substitute_food),
            joinedload(PantryItem.unit).selectinload(IngredientUnitModel.aliases),
        ]


class PantryItemPagination(PaginationBase):
    items: list[PantryItemOut]


class PutAwayRequest(MealieModel):
    item_ids: list[UUID4] | None = None
    """Shopping list item ids to put away; `None` means every checked item."""


class PutAwayResult(MealieModel):
    created: list[PantryItemOut]
    merged: list[PantryItemOut]
    removed_item_ids: list[UUID4]
