from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import UUID4, ConfigDict, field_validator, model_validator
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household.pantry import PantryItem
from mealie.db.models.recipe import IngredientFoodModel, IngredientFoodSubstitutionModel, IngredientUnitModel
from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField
from mealie.schema.household.group_shopping_list import ShoppingListItemOut
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientUnit
from mealie.schema.response.pagination import PaginationBase
from mealie.services.claude_context.shelf_life import estimate_shelf_life


class PantryLocation(StrEnum):
    fridge = "fridge"
    freezer = "freezer"
    cupboard = "cupboard"
    other = "other"


class PantrySource(StrEnum):
    shopping = "shopping"
    manual = "manual"
    leftover = "leftover"


class _PantryItemFields(MealieModel):
    """Columns shared by the write and read schemas. The blank-name validator lives on the write schemas
    only, so a row already stored with a blank name still loads instead of failing the whole list."""

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


class PantryItemCreate(_PantryItemFields):
    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PantryItemUpdate(PantryItemCreate):
    pass


class PantryShelfLife(MealieModel):
    """How long the item typically keeps, in days, once opened and sealed. An estimate, not a safety rule."""

    opened_days: int | None = None
    unopened_days: int | None = None
    source: Literal["food", "typical"]
    """`food`: set on the item's food; `typical`: Mealie's built-in table of common foods."""


class PantryItemOut(_PantryItemFields):
    id: UUID4
    group_id: UUID4
    household_id: UUID4

    food: IngredientFood | None = None
    unit: IngredientUnit | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)

    shelf_life: PantryShelfLife | None = None
    """Filled from the item itself on every read; whatever a client sends here is ignored."""

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _estimate_shelf_life(self) -> PantryItemOut:
        estimate = estimate_shelf_life(
            name=self.name,
            location=self.location.value,
            source=self.source.value,
            note=self.note,
            food_name=self.food.name if self.food else None,
            food_extras=self.food.extras if self.food else None,
        )
        self.shelf_life = (
            PantryShelfLife(
                opened_days=estimate.opened_days, unopened_days=estimate.unopened_days, source=estimate.source
            )
            if estimate
            else None
        )
        return self

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
    location: PantryLocation | None = None
    """Where the new rows go; `None` picks one per item from its label. A merge keeps the existing row's place."""


class PutAwayResult(MealieModel):
    created: list[PantryItemOut]
    merged: list[PantryItemOut]
    removed_item_ids: list[UUID4]


class AlreadyHaveRequest(MealieModel):
    location: PantryLocation = PantryLocation.cupboard
    """Where the new pantry row goes when the pantry holds nothing matching yet."""


class AlreadyHaveResult(MealieModel):
    removed_item: ShoppingListItemOut
    created_pantry_item: PantryItemOut | None = None
    """The pantry row this call created, or null when the pantry already held the item."""
