"""The TRMNL "Ce soir" screen data: which meal is tonight, what to buy, what is at home."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from mealie.schema.household.group_shopping_list import ShoppingListItemCreate, ShoppingListSave
from mealie.schema.household.pantry import PantryItemCreate, PantryItemOut, PantryLocation
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackCreate
from mealie.schema.household.trmnl import TrmnlState, TrmnlToBuy
from mealie.schema.labels.multi_purpose_label import MultiPurposeLabelSave
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry, SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import (
    CreateIngredientFoodSubstitution,
    IngredientFood,
    IngredientUnit,
    RecipeIngredient,
    SaveIngredientFood,
    SaveIngredientUnit,
)
from mealie.schema.user.user import PrivateUser
from mealie.services.claude_context.trmnl_service import TrmnlTonightService
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

TODAY = date(2026, 11, 11)
NOW = datetime(2026, 11, 11, 16, 0, tzinfo=UTC)


def _tonight(user: TestUser, now: datetime = NOW):
    private_user = user.repos.users.get_one(user.user_id)
    household = user.repos.households.get_one(user.household_id)
    assert isinstance(private_user, PrivateUser) and household is not None
    user.repos.session.expire_all()
    return TrmnlTonightService(user.repos, private_user, household).tonight(today=now.date(), now=now)


def _food(user: TestUser, name: str | None = None, **extra: Any) -> IngredientFood:
    return user.repos.ingredient_foods.create(
        SaveIngredientFood(name=name or random_string(10), group_id=user.group_id, **extra)
    )


def _recipe(user: TestUser, lines: list[RecipeIngredient] | None = None, **extra: Any) -> Recipe:
    return user.repos.recipes.create(
        Recipe(
            name=extra.pop("name", random_string(10)),
            user_id=user.user_id,
            group_id=user.group_id,
            household_id=user.household_id,
            recipe_ingredient=lines or [],
            **extra,
        )
    )


def _plan(
    user: TestUser,
    recipe: Recipe | None = None,
    entry_type: PlanEntryType = PlanEntryType.dinner,
    title: str = "",
    scale: float = 1.0,
    day: date = TODAY,
) -> ReadPlanEntry:
    return user.repos.meals.create(
        SavePlanEntry(
            date=day,
            entry_type=entry_type,
            title=title,
            recipe_id=recipe.id if recipe else None,
            recipe_scale=scale,
            group_id=user.group_id,
            user_id=user.user_id,
        )
    )


def _item(user: TestUser, name: str, food: IngredientFood | None = None, **extra: Any) -> PantryItemOut:
    return user.repos.pantry_items.create(PantryItemCreate(name=name, food_id=food.id if food else None, **extra))


@pytest.fixture
def user(unique_user_fn_scoped: TestUser) -> TestUser:
    """A fresh household per test: the screen reads the whole day's plan and pantry."""
    return unique_user_fn_scoped


# ------------------------------------------------------------------ picking tonight


def test_nothing_planned_lists_use_soon(user: TestUser):
    _item(user, "Épinards", quantity=1, use_by=TODAY + timedelta(days=1))
    _item(user, "Riz", quantity=1, use_by=TODAY + timedelta(days=30))

    out = _tonight(user)

    assert out.state == TrmnlState.nothing_planned
    assert out.recipe is None
    assert [u.name for u in out.use_soon] == ["Épinards"]
    assert out.use_soon[0].when == "1 j"
    assert out.kicker == "AUJOURD'HUI · MERCREDI 11 NOV."
    assert out.generated_at == "16:00"


def test_use_soon_worst_first(user: TestUser):
    _item(user, "Yaourt", quantity=1, use_by=TODAY + timedelta(days=2))
    _item(user, "Crème", quantity=1, use_by=TODAY - timedelta(days=1))

    out = _tonight(user)

    assert [(u.name, u.when) for u in out.use_soon] == [("Crème", "dépassé"), ("Yaourt", "2 j")]


def test_nothing_planned_shows_the_pantry_by_place(user: TestUser):
    _item(user, "Pâtes", quantity=1)  # cupboard by default
    _item(user, "Petits pois", quantity=1, location=PantryLocation.freezer)
    _item(user, "Lait", quantity=1, location=PantryLocation.fridge, use_by=TODAY + timedelta(days=5))
    _item(user, "Crème", quantity=1, location=PantryLocation.fridge, use_by=TODAY - timedelta(days=1))

    out = _tonight(user)

    assert [(p.name, p.count, p.items) for p in out.places] == [
        ("Frigo", 2, ["Crème", "Lait"]),
        ("Congélateur", 1, ["Petits pois"]),
        ("Placard", 1, ["Pâtes"]),
    ]
    assert [(u.name, u.place) for u in out.use_soon] == [("Crème", "Frigo")]


def test_items_without_quantity_are_not_shown(user: TestUser):
    _item(user, "Farine")  # a staple kept without a quantity
    _item(user, "Sucre", quantity=1)
    _item(user, "Crème", location=PantryLocation.fridge, use_by=TODAY - timedelta(days=1))

    out = _tonight(user)

    assert [(p.name, p.count, p.items) for p in out.places] == [("Placard", 1, ["Sucre"])]
    assert out.use_soon == []


def test_places_group_by_kind_of_food_with_quantities(user: TestUser):
    g = _unit(user, "gramme", "g")
    label = user.repos.group_multi_purpose_labels.create(
        MultiPurposeLabelSave(name="Épicerie sucrée", group_id=user.group_id)
    )
    chocolat = _food(user, "Chocolat noir", label_id=label.id)
    _item(user, "Riz", quantity=1000, unit_id=g.id)
    _item(user, "Sel", quantity=500, unit_id=g.id)
    _item(user, "Pâtes", quantity=500, unit_id=g.id)
    _item(user, "Pâtes", quantity=250, unit_id=g.id)  # one line with the first: same name and unit
    _item(user, "Tablette", chocolat, quantity=2)
    _item(user, "Bidule", quantity=1)

    (cupboard,) = _tonight(user).places

    assert cupboard.count == 5
    assert [(g.name, [(i.name, i.quantity) for i in g.items]) for g in cupboard.groups] == [
        ("Féculents", [("Pâtes", "750 g"), ("Riz", "1000 g")]),  # the pantry's order: no dates, so by name
        ("Assaisonner", [("Sel", "500 g")]),
        ("Épicerie sucrée", [("Tablette", "2")]),
        ("Autres", [("Bidule", "1")]),
    ]


def test_places_only_when_nothing_planned(user: TestUser):
    _item(user, "Lait", location=PantryLocation.fridge)
    _plan(user, _recipe(user))

    assert _tonight(user).places == []


def test_lunch_past_shows_dinner(user: TestUser):
    _plan(user, _recipe(user), PlanEntryType.lunch)
    _plan(user, None, PlanEntryType.dinner, title="Pizza")

    out = _tonight(user)

    assert out.state == TrmnlState.no_recipe
    assert out.recipe is not None and out.recipe.name == "Pizza"


def test_two_dinners_recipe_wins(user: TestUser):
    _plan(user, None, title="Restes")
    recipe = _recipe(user)
    _plan(user, recipe)

    out = _tonight(user)

    assert out.state == TrmnlState.planned
    assert out.recipe is not None and out.recipe.name == recipe.name


def test_past_days_and_beyond_a_week_ignored(user: TestUser):
    _plan(user, _recipe(user), day=TODAY - timedelta(days=1))
    _plan(user, _recipe(user), day=TODAY + timedelta(days=7))

    assert _tonight(user).state == TrmnlState.nothing_planned


def test_cooked_entry_skipped(user: TestUser):
    entry = _plan(user, None, title="Soupe")
    user.repos.meals.patch(entry.id, {"cooked_at": NOW})

    assert _tonight(user).state == TrmnlState.nothing_planned


def test_dessert_ignored(user: TestUser):
    _plan(user, _recipe(user), PlanEntryType.dessert)

    assert _tonight(user).state == TrmnlState.nothing_planned


def test_planned_facts_and_kicker(user: TestUser):
    recipe = _recipe(user, total_time_seconds=2100, recipe_servings=4)
    user.repos.recipe_feedback.create(
        {
            **RecipeFeedbackCreate(
                recipe_id=recipe.id, verdict=FeedbackVerdict.loved, made_on=date(2026, 10, 1)
            ).model_dump(),
            "user_id": user.user_id,
        }
    )
    _plan(user, recipe)

    out = _tonight(user)

    assert out.recipe is not None
    assert out.recipe.facts == "35 min · 4 portions · ♥ adoré la dernière fois"
    assert out.kicker.startswith("CE SOIR · ")


def test_planned_servings_follow_scale(user: TestUser):
    _plan(user, _recipe(user, recipe_servings=2), scale=2)

    out = _tonight(user)

    assert out.recipe is not None and out.recipe.facts == "4 portions"


def test_image_url_only_with_image(user: TestUser):
    _plan(user, _recipe(user))
    out = _tonight(user)
    assert out.recipe is not None and out.recipe.image_url is None


def test_image_url_with_image(user: TestUser):
    recipe = _recipe(user, image="abc")
    _plan(user, recipe)
    out = _tonight(user)
    assert out.recipe is not None and out.recipe.image_url is not None
    assert out.recipe.image_url.endswith(f"/api/media/recipes/{recipe.id}/images/min-original.webp")


# ------------------------------------------------------------------ what to buy, what is at home


def _unit(user: TestUser, name: str, abbreviation: str = "") -> IngredientUnit:
    return user.repos.ingredient_units.create(
        SaveIngredientUnit(
            name=name, abbreviation=abbreviation, use_abbreviation=bool(abbreviation), group_id=user.group_id
        )
    )


def _line(
    food: IngredientFood | None, quantity: float | None = None, unit: IngredientUnit | None = None, note: str = ""
) -> RecipeIngredient:
    return RecipeIngredient(food=food, quantity=quantity, unit=unit, note=note)


def _dinner(user: TestUser, lines: list[RecipeIngredient], scale: float = 1.0) -> Recipe:
    recipe = _recipe(user, lines)
    _plan(user, recipe, scale=scale)
    return recipe


def test_missing_food_to_buy(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    coco = _food(user, "Lait de coco")
    _dinner(user, [_line(coco, 400, ml)])

    out = _tonight(user)

    assert out.to_buy == [TrmnlToBuy(name="Lait de coco", quantity="400 ml", type="Conserves")]
    assert out.at_home == [] and out.to_check_count == 0 and out.ingredient_count == 1


def test_enough_at_home(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    coco = _food(user, "Lait de coco")
    _item(user, "Lait de coco", coco, quantity=500, unit_id=ml.id)
    _dinner(user, [_line(coco, 400, ml)])

    out = _tonight(user)

    assert out.to_buy == []
    assert [a.name for a in out.at_home] == ["Lait de coco"]
    assert out.ingredient_count == 1 and out.to_check_count == 0


def test_short_shows_left(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    coco = _food(user, "Lait de coco")
    _item(user, "Lait de coco", coco, quantity=100, unit_id=ml.id)
    _dinner(user, [_line(coco, 400, ml)])

    out = _tonight(user)

    assert [(b.quantity, b.left) for b in out.to_buy] == [("400 ml", "reste 100 ml")]
    assert out.at_home == []


def test_two_items_add_up(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    coco = _food(user, "Lait de coco")
    _item(user, "Lait de coco", coco, quantity=200, unit_id=ml.id)
    _item(user, "Lait de coco", coco, quantity=200, unit_id=ml.id)
    _dinner(user, [_line(coco, 400, ml)])

    out = _tonight(user)

    assert out.to_buy == [] and [a.name for a in out.at_home] == ["Lait de coco"]


def test_units_differ_to_check(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    can = _unit(user, "boîte")
    coco = _food(user, "Lait de coco")
    _item(user, "Lait de coco", coco, quantity=1, unit_id=can.id)
    _dinner(user, [_line(coco, 400, ml)])

    out = _tonight(user)

    assert out.to_buy == [] and [a.name for a in out.at_home] == ["Lait de coco"]
    assert out.to_check_count == 1


def test_food_without_quantity_in_pantry(user: TestUser):
    """At home, so not to buy; but kept without a quantity, so not listed, and the screen can't say all is there."""
    salt = _food(user, "Sel")
    _item(user, "Sel", salt)
    _dinner(user, [_line(salt)])

    out = _tonight(user)

    assert out.to_buy == [] and out.at_home == []
    assert out.to_check_count == 1 and out.ingredient_count == 1


def test_food_without_quantity_missing(user: TestUser):
    _dinner(user, [_line(_food(user, "Sel"))])

    out = _tonight(user)

    assert out.to_buy == [TrmnlToBuy(name="Sel", quantity=None, type="Assaisonner")]


def test_unparsed_line_to_check(user: TestUser):
    _dinner(user, [_line(None, note="une pincée de bonheur"), _line(None)])

    out = _tonight(user)

    assert out.to_check_count == 1 and out.to_buy == [] and out.ingredient_count == 0


def test_substitute_counts_at_home(user: TestUser):
    yaourt = _food(user, "Yaourt")
    creme = _food(user, "Crème", substitutions=[CreateIngredientFoodSubstitution(substitute_food_id=yaourt.id)])
    _item(user, "Yaourt grec", yaourt, quantity=30, use_by=TODAY + timedelta(days=1))
    _dinner(user, [_line(creme, 20)])

    out = _tonight(user)

    assert out.to_buy == []
    assert [(a.name, a.use_soon) for a in out.at_home] == [("Yaourt (pour Crème)", True)]


def test_on_list_mark(user: TestUser):
    oignon, ail = _food(user, "Oignon"), _food(user, "Ail")
    shopping_list = user.repos.group_shopping_lists.create(
        ShoppingListSave(name="Courses", group_id=user.group_id, user_id=user.user_id)
    )
    for food, checked in ((oignon, False), (ail, True)):
        user.repos.group_shopping_list_item.create(
            ShoppingListItemCreate(shopping_list_id=shopping_list.id, food_id=food.id, checked=checked, note="")
        )
    _dinner(user, [_line(oignon, 1), _line(ail, 2)])

    out = _tonight(user)

    assert [(b.name, b.on_list) for b in out.to_buy] == [("Oignon", True), ("Ail", False)]


def test_every_row_is_sent(user: TestUser):
    _dinner(user, [_line(_food(user, f"Aliment {i}"), 1) for i in range(10)])

    out = _tonight(user)

    assert len(out.to_buy) == 10 and out.to_buy_more == 0
    assert out.to_buy[0].name == "Aliment 0" and out.ingredient_count == 10


def test_rows_sorted_by_kind_of_food(user: TestUser):
    _dinner(
        user,
        [_line(_food(user, name), 1) for name in ("Farine", "Carotte", "Bidule", "Poulet", "Oignon")],
    )

    out = _tonight(user)

    assert [(b.name, b.type) for b in out.to_buy] == [
        ("Carotte", "Légumes"),
        ("Oignon", "Légumes"),
        ("Poulet", "Viandes"),
        ("Farine", "Pâtisserie"),
        ("Bidule", "Autres"),
    ]


def test_scaled_quantity(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    _dinner(user, [_line(_food(user, "Lait"), 200, ml)], scale=2)

    assert _tonight(user).to_buy[0].quantity == "400 ml"


def test_same_food_lines_summed(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    lait = _food(user, "Lait")
    _dinner(user, [_line(lait, 200, ml), _line(lait, 100, ml)])

    out = _tonight(user)

    assert [(b.name, b.quantity) for b in out.to_buy] == [("Lait", "300 ml")]


def test_use_soon_flag(user: TestUser):
    epinards = _food(user, "Épinards")
    _item(user, "Épinards", epinards, quantity=1, use_by=TODAY + timedelta(days=1))
    _dinner(user, [_line(epinards)])

    out = _tonight(user)

    assert [(a.name, a.use_soon) for a in out.at_home] == [("Épinards", True)]


# ------------------------------------------------------------------ review fixes


def test_dinner_done_does_not_fall_back_to_lunch(user: TestUser):
    _plan(user, _recipe(user), PlanEntryType.lunch)
    dinner = _plan(user, None, title="Soupe")
    user.repos.meals.patch(dinner.id, {"cooked_at": NOW})

    assert _tonight(user).state == TrmnlState.nothing_planned


def test_breakfast_done_still_shows_dinner(user: TestUser):
    breakfast = _plan(user, None, PlanEntryType.breakfast, title="Tartines")
    user.repos.meals.patch(breakfast.id, {"cooked_at": NOW})
    _plan(user, None, title="Soupe")

    out = _tonight(user)

    assert out.recipe is not None and out.recipe.name == "Soupe"


def test_substitute_not_enough_is_to_buy(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    yaourt = _food(user, "Yaourt")
    creme = _food(user, "Crème", substitutions=[CreateIngredientFoodSubstitution(substitute_food_id=yaourt.id)])
    _item(user, "Yaourt", yaourt, quantity=50, unit_id=ml.id)
    _dinner(user, [_line(creme, 400, ml)])

    out = _tonight(user)

    assert [(b.name, b.quantity) for b in out.to_buy] == [("Crème", "400 ml")]
    assert out.at_home == []


def test_substitute_unknown_amount_to_check(user: TestUser):
    ml = _unit(user, "millilitre", "ml")
    yaourt = _food(user, "Yaourt")
    creme = _food(user, "Crème", substitutions=[CreateIngredientFoodSubstitution(substitute_food_id=yaourt.id)])
    _item(user, "Yaourt", yaourt)
    _dinner(user, [_line(creme, 400, ml)])

    out = _tonight(user)

    # at home, but kept without a quantity: not listed, and never "Rien à acheter"
    assert out.to_buy == [] and out.at_home == [] and out.to_check_count == 1


def test_recipe_without_ingredients_is_to_check(user: TestUser):
    _dinner(user, [])

    out = _tonight(user)

    assert out.to_buy == [] and out.ingredient_count == 0 and out.to_check_count == 1


# ------------------------------------------------------------------ the next meal, not only tonight


def test_lunch_before_its_time_comes_first(user: TestUser):
    _plan(user, None, PlanEntryType.lunch, title="Salade")
    _plan(user, None, title="Soupe")

    out = _tonight(user, now=datetime(2026, 11, 11, 11, 0, tzinfo=UTC))

    assert out.recipe is not None and out.recipe.name == "Salade"
    assert out.kicker == "CE MIDI · MERCREDI 11 NOV."


def test_breakfast_in_the_morning(user: TestUser):
    _plan(user, None, PlanEntryType.breakfast, title="Tartines")

    out = _tonight(user, now=datetime(2026, 11, 11, 7, 0, tzinfo=UTC))

    assert out.kicker == "CE MATIN · MERCREDI 11 NOV."


def test_dinner_cooked_shows_tomorrow(user: TestUser):
    dinner = _plan(user, None, title="Soupe")
    user.repos.meals.patch(dinner.id, {"cooked_at": NOW})
    _plan(user, None, title="Curry", day=TODAY + timedelta(days=1))

    out = _tonight(user)

    assert out.recipe is not None and out.recipe.name == "Curry"
    assert out.kicker == "DEMAIN SOIR · JEUDI 12 NOV."


def test_late_evening_moves_to_tomorrow(user: TestUser):
    _plan(user, None, title="Soupe")
    _plan(user, None, PlanEntryType.lunch, title="Quiche", day=TODAY + timedelta(days=1))

    out = _tonight(user, now=datetime(2026, 11, 11, 21, 30, tzinfo=UTC))

    assert out.recipe is not None and out.recipe.name == "Quiche"
    assert out.kicker == "DEMAIN MIDI · JEUDI 12 NOV."


def test_later_this_week(user: TestUser):
    _plan(user, None, title="Lasagnes", day=TODAY + timedelta(days=3))

    out = _tonight(user)

    assert out.recipe is not None and out.recipe.name == "Lasagnes"
    assert out.kicker == "SAMEDI SOIR · 14 NOV."


def test_earliest_meal_of_a_later_day(user: TestUser):
    _plan(user, None, title="Lasagnes", day=TODAY + timedelta(days=2))
    _plan(user, None, PlanEntryType.lunch, title="Wraps", day=TODAY + timedelta(days=2))

    out = _tonight(user)

    assert out.recipe is not None and out.recipe.name == "Wraps"


def test_dinner_before_side(user: TestUser):
    _plan(user, None, PlanEntryType.side, title="Salade verte")
    _plan(user, None, title="Steak")

    out = _tonight(user)

    assert out.recipe is not None and out.recipe.name == "Steak"


def test_free_text_meal_lists_use_soon(user: TestUser):
    _item(user, "Crème", quantity=1, use_by=TODAY - timedelta(days=1))
    _plan(user, None, title="Pizza chez Marco")

    out = _tonight(user)

    assert out.state == TrmnlState.no_recipe
    assert [(u.name, u.when) for u in out.use_soon] == [("Crème", "dépassé")]
