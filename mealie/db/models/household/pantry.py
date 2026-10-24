import datetime
from typing import TYPE_CHECKING

from pydantic import ConfigDict
from sqlalchemy import Date, Float, ForeignKey, String, orm
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.guid import GUID
from ..recipe.ingredient import IngredientFoodModel, IngredientUnitModel

if TYPE_CHECKING:
    from .household import Household


class PantryItem(SqlAlchemyBase, BaseMixins):
    """Something the household has on hand, with its location and dates."""

    __tablename__ = "pantry_items"

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = orm.relationship("Household", back_populates="pantry_items")

    food_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, ForeignKey("ingredient_foods.id", ondelete="SET NULL"), index=True
    )
    food: Mapped[IngredientFoodModel | None] = orm.relationship(IngredientFoodModel, uselist=False)

    name: FilterableColumn[str] = mapped_column(String, nullable=False)
    quantity: FilterableColumn[float | None] = mapped_column(Float)

    unit_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("ingredient_units.id", ondelete="SET NULL"))
    unit: Mapped[IngredientUnitModel | None] = orm.relationship(IngredientUnitModel, uselist=False)

    location: FilterableColumn[str] = mapped_column(String, nullable=False, default="cupboard")
    bought_on: FilterableColumn[datetime.date | None] = mapped_column(Date)
    opened_on: FilterableColumn[datetime.date | None] = mapped_column(Date)
    use_by: FilterableColumn[datetime.date | None] = mapped_column(Date)
    source: FilterableColumn[str] = mapped_column(String, nullable=False, default="manual")
    note: FilterableColumn[str | None] = mapped_column(String)

    # Relationships are read-only views of the FK columns; never let auto_init build them.
    model_config = ConfigDict(exclude={"food", "unit", "household"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass
