from uuid import uuid4

import pytest

from mealie.schema.household.pantry import PantryItemOut
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientUnit, RecipeIngredient
from mealie.services.claude_context.pantry_usage import (
    grams_each,
    propose_for_food,
    propose_substitute,
    weight_from_note,
)

GRAMME = IngredientUnit(id=uuid4(), name="gramme", abbreviation="g")
KG = IngredientUnit(id=uuid4(), name="kilogramme", abbreviation="kg")
GOUSSE = IngredientUnit(id=uuid4(), name="gousse")
BOITE = IngredientUnit(id=uuid4(), name="boîte")
TSP = IngredientUnit(id=uuid4(), name="cuillère à café", abbreviation="tsp")
TBSP = IngredientUnit(id=uuid4(), name="cuillère à soupe", standard_quantity=1, standard_unit="tablespoon")
LITRE = IngredientUnit(id=uuid4(), name="litre", standard_quantity=1, standard_unit="liter")
BARE_GRAMME = IngredientUnit(id=uuid4(), name="gramme")
BARE_KG = IngredientUnit(id=uuid4(), name="kg")


def _food(name: str, **extras: str) -> IngredientFood:
    return IngredientFood(id=uuid4(), name=name, extras=extras or None)


def _line(
    food: IngredientFood, quantity: float | None, unit: IngredientUnit | None = None, note: str = ""
) -> RecipeIngredient:
    return RecipeIngredient(quantity=quantity, unit=unit, food=food, note=note)


def _item(food: IngredientFood, quantity: float | None, unit: IngredientUnit | None = None) -> PantryItemOut:
    return PantryItemOut(
        id=uuid4(),
        group_id=uuid4(),
        household_id=uuid4(),
        name=food.name,
        food_id=food.id,
        food=food,
        quantity=quantity,
        unit_id=unit.id if unit else None,
        unit=unit,
    )


def test_potato_weight_from_note():
    food = _food("pomme de terre")
    line = _line(food, 1, None, "environ 200 g, en petits dés")
    [p] = propose_for_food([line], [_item(food, 1000, GRAMME)], scale=1)
    assert (p.used, p.proposed_quantity, p.proposed_outcome, p.reason) == (200, 800, "some_left", "weight_from_note")


def test_garlic_same_unit_used_up():
    food = _food("ail")
    [p] = propose_for_food([_line(food, 1, GOUSSE)], [_item(food, 1, GOUSSE)], 1)
    assert (p.proposed_quantity, p.proposed_outcome, p.reason) == (0, "used_up", "subtracted")


def test_paprika_units_differ():
    food = _food("paprika")
    lines = [_line(food, 1, TSP), _line(food, 0.5, TSP)]
    [p] = propose_for_food(lines, [_item(food, 1, BOITE)], 1)
    assert (p.used, p.proposed_quantity, p.proposed_outcome, p.reason) == (None, 1, "some_left", "units_differ")


def test_oil_small_amount():
    food = _food("huile")
    line = _line(food, 1, TBSP)
    [p] = propose_for_food([line, line], [_item(food, 1, LITRE)], 1)
    assert (p.proposed_quantity, p.proposed_outcome, p.reason) == (1, "some_left", "small_amount")
    assert p.used == pytest.approx(0.03, abs=1e-3)


def test_converted_between_pint_units():
    food = _food("farine")
    [p] = propose_for_food([_line(food, 500, GRAMME)], [_item(food, 2, KG)], 1)
    assert (p.used, p.proposed_quantity, p.reason) == (0.5, 1.5, "converted")


def test_sausage_substitute():
    lardon = _food("lardon")
    saucisse = _food("saucisse de porc")
    line = _line(lardon, 150, GRAMME)
    p = propose_substitute(line, _item(saucisse, 300, GRAMME), 1)
    assert (p.used, p.proposed_quantity, p.replaces_reference_id) == (150, 150, line.reference_id)


def test_scale_doubles_and_lines_sum():
    food = _food("riz")
    lines = [_line(food, 100, GRAMME), _line(food, 100, GRAMME)]
    [p] = propose_for_food(lines, [_item(food, 1000, GRAMME)], scale=2)
    assert (p.used, p.proposed_quantity) == (400, 600)


def test_spill_across_items_and_untouched_second():
    food = _food("farine")
    items = [_item(food, 200, GRAMME), _item(food, 500, GRAMME)]

    first, second = propose_for_food([_line(food, 300, GRAMME)], items, 1)
    assert (first.proposed_outcome, first.proposed_quantity) == ("used_up", 0)
    assert (second.proposed_outcome, second.proposed_quantity) == ("some_left", 400)

    first, second = propose_for_food([_line(food, 100, GRAMME)], items, 1)
    assert (first.proposed_outcome, first.proposed_quantity) == ("some_left", 100)
    assert (second.proposed_outcome, second.reason, second.used, second.proposed_quantity) == ("none", None, None, None)


def test_grams_each_from_food_extras():
    food = _food("pomme de terre", grams_each="150")
    assert grams_each(food) == 150
    [p] = propose_for_food([_line(food, 2)], [_item(food, 1, KG)], 1)
    assert (p.used, p.proposed_quantity, p.reason) == (0.3, 0.7, "weight_from_food")


def test_weight_in_grams_to_pieces_from_food():
    food = _food("oignon", grams_each="100")
    [p] = propose_for_food([_line(food, 300, GRAMME)], [_item(food, 5)], 1)
    assert (p.used, p.proposed_quantity, p.reason) == (3, 2, "weight_from_food")


def test_grams_each_missing_or_bad():
    assert grams_each(None) is None
    assert grams_each(_food("x")) is None
    assert grams_each(_food("x", grams_each="0")) is None
    assert grams_each(_food("x", grams_each="beaucoup")) is None


def test_weight_from_note_parsing():
    assert weight_from_note("environ 200 g") == 200
    assert weight_from_note("1,5 kg") == 1500
    assert weight_from_note("200g") == 200
    assert weight_from_note("1 pincée") is None
    assert weight_from_note(None) is None


def test_reason_precedence():
    food = _food("mix", grams_each="100")
    lines = [_line(food, 100, GRAMME), _line(food, 1, None, "200 g")]
    [p] = propose_for_food(lines, [_item(food, 1000, GRAMME)], 1)
    assert (p.used, p.reason) == (300, "weight_from_note")


def test_no_quantity():
    food = _food("sel")
    [p] = propose_for_food([_line(food, 1, GRAMME)], [_item(food, 0, GRAMME)], 1)
    assert (p.proposed_outcome, p.proposed_quantity, p.reason) == ("some_left", 0, "no_quantity")

    [p] = propose_for_food([_line(food, None, GRAMME)], [_item(food, 10, GRAMME)], 1)
    assert (p.proposed_outcome, p.proposed_quantity, p.reason) == ("some_left", 10, "no_quantity")


def test_unknown_unit_names_never_raise():
    food = _food("farine")
    [p] = propose_for_food([_line(food, 100, BARE_GRAMME)], [_item(food, 1, BARE_KG)], 1)
    assert (p.proposed_outcome, p.proposed_quantity, p.reason) == ("some_left", 1, "units_differ")


def test_item_after_need_covered_gets_none_even_if_units_differ():
    food = _food("farine")
    items = [_item(food, 100, GRAMME), _item(food, 5, GOUSSE)]
    [first, second] = propose_for_food([_line(food, 100, GRAMME)], items, 1)
    assert first.proposed_outcome == "used_up"
    assert (second.proposed_outcome, second.used, second.proposed_quantity) == ("none", None, None)
