from collections.abc import Callable

from mealie.db.models.recipe import IngredientFoodModel
from mealie.schema.household.group_shopping_list import ShoppingListItemOut
from mealie.schema.household.pantry import PantryItemOut
from mealie.schema.recipe.recipe_ingredient import IngredientFood
from mealie.services.claude_context.recipe_writer import food_name_variants


def _name_keys(name: str) -> set[str]:
    key = IngredientFoodModel.normalize(name)
    return {key, *food_name_variants(key)}


def food_matcher(foods: list[IngredientFood]) -> Callable[[PantryItemOut], bool]:
    """Whether a pantry item is one of `foods`: by `food_id`, or (items without a food) by the food's name or
    its simple singular/plural, case-insensitively."""
    food_ids: set[str] = set()
    names: set[str] = set()
    for food in foods:
        food_ids.add(str(food.id))
        names.update(_name_keys(food.name))

    def matches(item: PantryItemOut) -> bool:
        if item.food_id is not None:
            return str(item.food_id) in food_ids
        return IngredientFoodModel.normalize(item.name) in names

    return matches


def shopping_item_matcher(item: ShoppingListItemOut) -> Callable[[PantryItemOut], bool]:
    """Whether a pantry item is what a shopping list item asks for.

    An item with a food uses `food_matcher`. A food-less item matches by its note, normalised with its simple
    singular/plural, against the pantry item's food name (or its own name when it has no food). A blank note
    matches nothing."""
    if item.food is not None:
        return food_matcher([item.food])

    names = _name_keys(item.note) if item.note and item.note.strip() else set()

    def matches(pantry_item: PantryItemOut) -> bool:
        if not names:
            return False
        name = pantry_item.food.name if pantry_item.food is not None else pantry_item.name
        return IngredientFoodModel.normalize(name) in names

    return matches
