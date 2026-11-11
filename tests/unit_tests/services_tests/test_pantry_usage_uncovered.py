"""Whether the pantry holds enough of a food for a recipe (`uncovered_fraction`)."""

from uuid import uuid4

import pytest

from mealie.schema.household.pantry import PantryItemOut
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientUnit, RecipeIngredient
from mealie.services.claude_context.pantry_usage import uncovered_fraction

ML = IngredientUnit(id=uuid4(), name="millilitre", abbreviation="ml", standard_quantity=1, standard_unit="milliliter")
PIECE = IngredientUnit(id=uuid4(), name="pièce")
FOOD = IngredientFood(id=uuid4(), name="lait de coco")


def _line(quantity: float | None, unit: IngredientUnit | None = ML) -> RecipeIngredient:
    return RecipeIngredient(quantity=quantity, unit=unit, food=FOOD, note="")


def _item(quantity: float | None, unit: IngredientUnit | None = ML) -> PantryItemOut:
    return PantryItemOut(
        id=uuid4(),
        group_id=uuid4(),
        household_id=uuid4(),
        name=FOOD.name,
        food_id=FOOD.id,
        food=FOOD,
        quantity=quantity,
        unit_id=unit.id if unit else None,
        unit=unit,
    )


def test_enough():
    assert uncovered_fraction([_line(400)], [_item(500)], 1) == 0.0


def test_exactly_enough():
    assert uncovered_fraction([_line(400)], [_item(400)], 1) == 0.0


def test_short():
    assert uncovered_fraction([_line(400)], [_item(100)], 1) == pytest.approx(0.75)


def test_two_items_add_up():
    assert uncovered_fraction([_line(400)], [_item(200), _item(200)], 1) == pytest.approx(0.0)


def test_units_differ_unknown():
    assert uncovered_fraction([_line(2, PIECE)], [_item(500)], 1) is None


def test_item_without_quantity_unknown():
    assert uncovered_fraction([_line(400)], [_item(None)], 1) is None


def test_scale():
    assert uncovered_fraction([_line(200)], [_item(300)], 2) == pytest.approx(0.25)


def test_unknown_item_after_enough_is_covered():
    assert uncovered_fraction([_line(400)], [_item(500), _item(None)], 1) == 0.0


def test_no_items_nothing_covered():
    assert uncovered_fraction([_line(400)], [], 1) == 1.0
