"""The kind of food a name is, for grouping the TRMNL screen."""

import pytest

from mealie.services.claude_context.food_type import OTHER, food_type, type_rank


@pytest.mark.parametrize(
    "name, kind",
    [
        ("pomme de terre", "Féculents"),
        ("Pomme", "Fruits"),
        ("lait de coco", "Conserves"),
        ("Lait", "Crèmerie"),
        ("laitue", "Légumes"),
        ("oignon frit", "Condiments"),
        ("Oignon", "Légumes"),
        ("huile d'olive", "Assaisonner"),
        ("Gruyère râpé", "Fromages"),
        ("Œufs", "Crèmerie"),
        ("épinards hachés", "Légumes"),
        ("tomates concassées", "Conserves"),
        ("noix de cajou", "Fruits secs"),
        ("maïzena", "Pâtisserie"),
        ("knacki", "Viandes"),
        ("frites", "Féculents"),
        ("chicken breast", "Viandes"),
        ("bidule", OTHER),
    ],
)
def test_name_table(name: str, kind: str):
    assert food_type(name) == kind


def test_label_wins():
    assert food_type("Riz", "Épicerie") == "Épicerie"
    assert food_type("Riz", "  ") == "Féculents"


def test_rank_puts_the_table_first_then_labels_then_others():
    kinds = ["Autres", "Zeste", "Pâtisserie", "Épicerie", "Légumes"]
    assert sorted(kinds, key=type_rank) == ["Légumes", "Pâtisserie", "Épicerie", "Zeste", "Autres"]
