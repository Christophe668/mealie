from uuid import uuid4

from mealie.schema.household.group_shopping_list import ShoppingListItemOut
from mealie.schema.household.pantry import PantryItemOut
from mealie.schema.recipe.recipe_ingredient import IngredientFood
from mealie.services.claude_context.pantry_matching import food_matcher, shopping_item_matcher


def _food(name: str) -> IngredientFood:
    return IngredientFood(id=uuid4(), name=name)


def _pantry(name: str, food: IngredientFood | None = None) -> PantryItemOut:
    return PantryItemOut(
        id=uuid4(),
        group_id=uuid4(),
        household_id=uuid4(),
        name=name,
        food_id=food.id if food else None,
        food=food,
    )


def _shopping(note: str = "", food: IngredientFood | None = None) -> ShoppingListItemOut:
    return ShoppingListItemOut(
        id=uuid4(),
        group_id=uuid4(),
        household_id=uuid4(),
        shopping_list_id=uuid4(),
        note=note,
        food_id=food.id if food else None,
        food=food,
    )


def test_food_matcher_by_id():
    lemon = _food("lemon")
    other = _food("lemon")  # same name, other food: a pantry row with a food matches by id only
    matches = food_matcher([lemon])

    assert matches(_pantry("anything", lemon))
    assert not matches(_pantry("lemon", other))


def test_food_matcher_foodless_row_by_name_plural():
    matches = food_matcher([_food("lemon")])

    assert matches(_pantry("Lemons"))
    assert not matches(_pantry("Limes"))


def test_shopping_item_matcher_with_food_uses_food_matcher():
    lemon = _food("lemon")
    matches = shopping_item_matcher(_shopping(food=lemon))

    assert matches(_pantry("x", lemon))
    assert matches(_pantry("Lemons"))
    assert not matches(_pantry("Limes"))


def test_shopping_item_matcher_foodless_note_matches_pantry_food_name():
    matches = shopping_item_matcher(_shopping("Lemon"))

    assert matches(_pantry("Citrus", _food("lemons")))
    assert matches(_pantry("Lemons"))
    assert not matches(_pantry("Limes", _food("limes")))


def test_shopping_item_matcher_blank_note_matches_nothing():
    for note in ("", "   "):
        matches = shopping_item_matcher(_shopping(note))
        assert not matches(_pantry("", None)) and not matches(_pantry("Lemons"))
