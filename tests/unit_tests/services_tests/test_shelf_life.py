import pytest

from mealie.services.claude_context.shelf_life import (
    FREEZER_DAYS,
    LEFTOVER_DAYS,
    THAWED_DAYS,
    ShelfLife,
    estimate_shelf_life,
    typical_days,
)


def _estimate(name: str, location: str = "cupboard", source: str = "manual", **kwargs) -> ShelfLife | None:
    return estimate_shelf_life(name=name, location=location, source=source, **kwargs)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Baguette", (2, 2)),
        ("baguettes", (2, 2)),
        ("Pommes de terre", (30, 30)),
        ("Crème fraîche", (5, 14)),
        ("GRUYÈRE", (21, 60)),
        ("oignon frit", (60, 180)),  # the longer keyword beats "oignon"
        ("oignons", (30, 30)),
        ("huile d'olive", (180, 540)),  # not the "olive" of the jars row
        ("lait de coco", (4, 180)),  # not fresh milk
        ("noix de cajou", (60, 180)),
        ("Spaghetti", (365, 730)),
        ("champagne", None),  # "pain" only matches as a whole word
        ("", None),
    ],
)
def test_typical_days(text: str, expected: tuple[int, int] | None):
    assert typical_days(text) == expected


def test_unknown_item_has_no_estimate():
    assert _estimate("Birthday candles") is None


def test_table_estimate_is_typical():
    assert _estimate("Milk", location="fridge") == ShelfLife(4, 7, "typical")


def test_food_name_is_matched_too():
    assert _estimate("Le bon", food_name="beurre") == ShelfLife(30, 60, "typical")


def test_note_is_used_only_when_the_names_match_nothing():
    assert _estimate("Ail", note="hachée") == ShelfLife(7, 60, "typical")
    assert _estimate("Something", note="sliced bread") == ShelfLife(5, 7, "typical")


def test_freezer_wins_over_everything():
    assert _estimate("Baguette", location="freezer") == ShelfLife(*FREEZER_DAYS, "typical")
    extras = {"shelf_life_days_opened": "2"}
    assert _estimate("Chicken", location="freezer", food_extras=extras) == ShelfLife(*FREEZER_DAYS, "typical")


def test_frozen_food_outside_the_freezer_keeps_a_day():
    assert _estimate("Frite", note="frites fines surgelées") == ShelfLife(*THAWED_DAYS, "typical")
    assert _estimate("Frozen peas", location="fridge") == ShelfLife(*THAWED_DAYS, "typical")


def test_food_extras_win_and_missing_ones_come_from_the_table():
    extras = {"shelf_life_days_opened": "10"}
    assert _estimate("Milk", food_extras=extras) == ShelfLife(10, 7, "food")


@pytest.mark.parametrize("bad", ["not a number", "0", "-3", True, 2.5, None])
def test_unusable_food_extras_are_ignored(bad):
    extras = {"shelf_life_days_opened": bad}
    assert _estimate("Milk", food_extras=extras) == ShelfLife(4, 7, "typical")


def test_leftovers_keep_three_days_whatever_the_food():
    assert _estimate("Chili sin carne", source="leftover", location="fridge") == ShelfLife(*LEFTOVER_DAYS, "typical")
    # Cooked rice is not dry rice.
    assert _estimate("Riz", source="leftover") == ShelfLife(*LEFTOVER_DAYS, "typical")
    assert _estimate("Riz", source="leftover", location="freezer") == ShelfLife(*FREEZER_DAYS, "typical")
