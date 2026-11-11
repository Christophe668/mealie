"""The TRMNL "Ce soir" screen data: which meal is tonight, what to buy, what is at home."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from mealie.schema.household.pantry import PantryItemCreate, PantryItemOut
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackCreate
from mealie.schema.household.trmnl import TrmnlState
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry, SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import IngredientFood, RecipeIngredient, SaveIngredientFood
from mealie.schema.user.user import PrivateUser
from mealie.services.claude_context.trmnl_service import TrmnlTonightService
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

TODAY = date(2026, 11, 11)
NOW = datetime(2026, 11, 11, 16, 0)


def _tonight(user: TestUser):
    private_user = user.repos.users.get_one(user.user_id)
    household = user.repos.households.get_one(user.household_id)
    assert isinstance(private_user, PrivateUser) and household is not None
    user.repos.session.expire_all()
    return TrmnlTonightService(user.repos, private_user, household).tonight(today=TODAY, now=NOW)


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
    _item(user, "Épinards", use_by=TODAY + timedelta(days=1))
    _item(user, "Riz", use_by=TODAY + timedelta(days=30))

    out = _tonight(user)

    assert out.state == TrmnlState.nothing_planned
    assert out.recipe is None
    assert [u.name for u in out.use_soon] == ["Épinards"]
    assert out.use_soon[0].when == "1 j"
    assert out.kicker == "CE SOIR · MERCREDI 11 NOV."
    assert out.generated_at == "16:00"


def test_use_soon_worst_first(user: TestUser):
    _item(user, "Yaourt", use_by=TODAY + timedelta(days=2))
    _item(user, "Crème", use_by=TODAY - timedelta(days=1))

    out = _tonight(user)

    assert [(u.name, u.when) for u in out.use_soon] == [("Crème", "dépassé"), ("Yaourt", "2 j")]


def test_dinner_beats_lunch_with_recipe(user: TestUser):
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


def test_other_days_ignored(user: TestUser):
    _plan(user, _recipe(user), day=TODAY - timedelta(days=1))
    _plan(user, _recipe(user), day=TODAY + timedelta(days=1))

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
