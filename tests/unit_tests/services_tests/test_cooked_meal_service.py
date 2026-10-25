from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mealie.core.exceptions import NoEntryFound
from mealie.schema.household.cooked_meal import (
    CookedFeedback,
    CookedLeftovers,
    CookedMealCreate,
    CookedPantryOutcome,
    PantryOutcome,
)
from mealie.schema.household.household_profile import MealPreferencesUpdate
from mealie.schema.household.pantry import PantryItemCreate, PantryItemOut, PantryLocation, PantrySource
from mealie.schema.household.recipe_feedback import FeedbackVerdict
from mealie.schema.meal_plan.new_meal import ReadPlanEntry, SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import IngredientFood, RecipeIngredient, SaveIngredientFood
from mealie.schema.user.user import PrivateUser
from mealie.services.claude_context.cooked_meal_service import (
    AlreadyCookedError,
    CookedMealService,
    PantryItemNotInRecipeError,
)
from mealie.services.claude_context.household_profile_service import HouseholdProfileService
from mealie.services.claude_context.recipe_feedback_service import FutureMadeOnError
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

# `record` refuses a cooking date later than the server's tomorrow, so tests use the real today.
TODAY = datetime.now().astimezone().date()


def _service(user: TestUser) -> CookedMealService:
    private_user = user.repos.users.get_one(user.user_id)
    household = user.repos.households.get_one(user.household_id)
    assert isinstance(private_user, PrivateUser) and household is not None
    return CookedMealService(user.repos, private_user, household)


def _food(user: TestUser, name: str | None = None) -> IngredientFood:
    return user.repos.ingredient_foods.create(
        SaveIngredientFood(name=name or random_string(10), group_id=user.group_id)
    )


def _recipe(user: TestUser, foods: list[IngredientFood] | None = None, servings: float = 0) -> Recipe:
    return user.repos.recipes.create(
        Recipe(
            name=random_string(10),
            user_id=user.user_id,
            group_id=user.group_id,
            household_id=user.household_id,
            recipe_servings=servings,
            recipe_ingredient=[RecipeIngredient(note="", food=food, quantity=1) for food in foods or []],
        )
    )


def _item(user: TestUser, name: str, food: IngredientFood | None = None, **extra: Any) -> PantryItemOut:
    return user.repos.pantry_items.create(PantryItemCreate(name=name, food_id=food.id if food else None, **extra))


def _plan(user: TestUser, recipe: Recipe, day: date, scale: float = 1.0) -> ReadPlanEntry:
    return user.repos.meals.create(
        SavePlanEntry(date=day, recipe_id=recipe.id, recipe_scale=scale, group_id=user.group_id, user_id=user.user_id)
    )


def _entry(user: TestUser, entry_id: int) -> ReadPlanEntry:
    user.repos.session.expire_all()
    entry = user.repos.meals.get_one(entry_id)
    assert entry is not None
    return entry


def _last_made(user: TestUser, recipe: Recipe) -> datetime | None:
    user.repos.session.expire_all()
    household_recipe = user.repos.household_recipes.get_by_recipe(recipe.id)
    return household_recipe.last_made if household_recipe else None


def _noon(day: date) -> datetime:
    return datetime.combine(day, time(12)).astimezone()


def _rating(user: TestUser, recipe: Recipe) -> float | None:
    rating = user.repos.user_ratings.get_by_user_and_recipe(user.user_id, recipe.id)
    return rating.rating if rating else None


def _snapshot(user: TestUser, recipe: Recipe, entry_ids: list[int]) -> dict[str, Any]:
    user.repos.session.expire_all()
    return {
        "pantry": sorted(
            (str(i.id), i.name, i.quantity, i.opened_on, i.use_by) for i in user.repos.pantry_items.ordered()
        ),
        "feedback": user.repos.recipe_feedback.page_newest_first(1, 100, recipe.id).total,
        "cooked_at": [_entry(user, entry_id).cooked_at for entry_id in entry_ids],
        "last_made": _last_made(user, recipe),
        "rating": _rating(user, recipe),
        "timeline_events": user.repos.recipe_timeline_events.count_all(match_key="recipe_id", match_value=recipe.id),
    }


# ------------------------------------------------------------------ pantry check


def test_pantry_check_matches_food_and_name_variants(unique_user: TestUser):
    tag = random_string(8)
    spaghetti = _food(unique_user, f"{tag} spaghetti")
    egg = _food(unique_user, f"{tag} egg")
    recipe = unique_user.repos.recipes.create(
        Recipe(
            name=random_string(10),
            user_id=unique_user.user_id,
            group_id=unique_user.group_id,
            recipe_ingredient=[
                RecipeIngredient(note="", food=spaghetti, quantity=200),
                RecipeIngredient(note="", food=egg, quantity=2),
                RecipeIngredient(note="salt to taste"),
            ],
        )
    )
    in_pantry = _item(unique_user, spaghetti.name, spaghetti)
    eggs = _item(unique_user, f"{tag.upper()} Eggs")
    _item(unique_user, f"{tag} rice")
    _item(unique_user, "salt")

    out = _service(unique_user).pantry_check(recipe.id, TODAY)

    assert {item.name for item in out.items} == {in_pantry.name, eggs.name}
    assert out.meal_plan_entry_id is None


def test_pantry_check_keeps_pantry_order(unique_user: TestUser):
    food_a, food_b = _food(unique_user), _food(unique_user)
    recipe = _recipe(unique_user, [food_a, food_b])
    later = _item(unique_user, food_a.name, food_a, use_by=TODAY + timedelta(days=9))
    sooner = _item(unique_user, food_b.name, food_b, use_by=TODAY + timedelta(days=1))

    out = _service(unique_user).pantry_check(recipe.id, TODAY)

    assert [item.id for item in out.items] == [sooner.id, later.id]


def test_pantry_check_unknown_recipe(unique_user: TestUser):
    with pytest.raises(NoEntryFound):
        _service(unique_user).pantry_check(uuid4(), TODAY)


def test_suggested_portions(unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    service = _service(user)
    four = _recipe(user, servings=4)
    two = _recipe(user, servings=2)

    assert service.pantry_check(four.id, TODAY).suggested_leftover_portions == 0  # no default_servings yet

    private_user = user.repos.users.get_one(user.user_id)
    assert isinstance(private_user, PrivateUser)
    profile = HouseholdProfileService(user.repos, private_user)
    profile.update_preferences(MealPreferencesUpdate(default_servings=2))

    assert service.pantry_check(four.id, TODAY).suggested_leftover_portions == 2
    assert service.pantry_check(four.id, TODAY, scale=2).suggested_leftover_portions == 6

    # without a scale, the matched entry's scale applies
    entry = _plan(user, four, TODAY, scale=1.5)
    out = service.pantry_check(four.id, TODAY)
    assert (out.suggested_leftover_portions, out.meal_plan_entry_id) == (4, entry.id)

    profile.update_preferences(MealPreferencesUpdate(default_servings=4))
    assert service.pantry_check(two.id, TODAY).suggested_leftover_portions == 0


# ------------------------------------------------------------------ entry matching


def test_find_entry_rules(unique_user: TestUser, h2_user: TestUser):
    service = _service(unique_user)
    yesterday = TODAY - timedelta(days=1)

    recipe = _recipe(unique_user)
    _plan(h2_user, recipe, TODAY)  # another household's entry never matches
    yesterdays = _plan(unique_user, recipe, yesterday)
    todays = _plan(unique_user, recipe, TODAY)

    found = service.find_entry(recipe.id, TODAY)
    assert found is not None and found.id == todays.id

    unique_user.repos.meals.patch(todays.id, {"cooked_at": datetime.now(UTC)})
    found = service.find_entry(recipe.id, TODAY)
    assert found is not None and found.id == yesterdays.id

    old = _recipe(unique_user)
    _plan(unique_user, old, TODAY - timedelta(days=2))
    assert service.find_entry(old.id, TODAY) is None

    other = _recipe(unique_user)
    _plan(h2_user, other, TODAY)
    assert service.find_entry(other.id, TODAY) is None


def test_find_entry_same_day_lowest_id(unique_user: TestUser):
    recipe = _recipe(unique_user)
    first = _plan(unique_user, recipe, TODAY)
    _plan(unique_user, recipe, TODAY)

    found = _service(unique_user).find_entry(recipe.id, TODAY)
    assert found is not None and found.id == first.id


# ------------------------------------------------------------------ record


def test_record_full(unique_user: TestUser):
    food_a, food_b = _food(unique_user), _food(unique_user)
    recipe = _recipe(unique_user, [food_a, food_b])
    entry = _plan(unique_user, recipe, TODAY)
    used = _item(unique_user, food_a.name, food_a)
    left = _item(unique_user, food_b.name, food_b, quantity=3)

    out = _service(unique_user).record(
        CookedMealCreate(
            recipe_id=recipe.id,
            cooked_on=TODAY,
            pantry=[
                CookedPantryOutcome(pantry_item_id=used.id, outcome=PantryOutcome.used_up),
                CookedPantryOutcome(pantry_item_id=left.id, outcome=PantryOutcome.some_left),
            ],
            leftovers=CookedLeftovers(portions=2),
            feedback=CookedFeedback(verdict=FeedbackVerdict.loved, effort=2),
        )
    )

    assert out.meal_plan_entry is not None and out.meal_plan_entry.id == entry.id
    stored = _entry(unique_user, entry.id)
    # local noon of the cooking date, stored as UTC
    assert stored.cooked_at is not None
    assert stored.cooked_at.replace(tzinfo=stored.cooked_at.tzinfo or UTC) == _noon(TODAY)
    assert stored.recipe_id == recipe.id and stored.date == TODAY  # nothing else changed on the entry

    assert out.removed_item_ids == [used.id]
    assert unique_user.repos.pantry_items.get_one(used.id) is None
    kept = unique_user.repos.pantry_items.get_one(left.id)
    assert kept is not None and kept.opened_on == TODAY and kept.quantity == 3
    assert [item.id for item in out.kept_items] == [left.id]

    assert out.leftover is not None
    leftover = unique_user.repos.pantry_items.get_one(out.leftover.id)
    assert leftover is not None
    assert leftover.name == f"Leftover {recipe.name}"
    assert leftover.source == PantrySource.leftover
    assert (leftover.quantity, leftover.unit_id, leftover.note) == (2, None, "portions")
    assert leftover.food_id is None
    assert leftover.location == PantryLocation.fridge
    assert leftover.bought_on == TODAY
    assert leftover.use_by == TODAY + timedelta(days=3)

    assert out.feedback is not None and out.feedback.verdict == FeedbackVerdict.loved
    assert out.feedback.effort == 2 and out.feedback.made_on == TODAY
    assert unique_user.repos.recipe_feedback.page_newest_first(1, 10, recipe.id).total == 1
    assert _last_made(unique_user, recipe) == _noon(TODAY)


def test_record_some_left_keeps_opened_on(unique_user: TestUser):
    food = _food(unique_user)
    recipe = _recipe(unique_user, [food])
    opened = TODAY - timedelta(days=5)
    item = _item(unique_user, food.name, food, opened_on=opened)

    out = _service(unique_user).record(
        CookedMealCreate(
            recipe_id=recipe.id,
            cooked_on=TODAY,
            pantry=[CookedPantryOutcome(pantry_item_id=item.id, outcome=PantryOutcome.some_left)],
        )
    )

    stored = unique_user.repos.pantry_items.get_one(item.id)
    assert stored is not None and stored.opened_on == opened
    assert out.meal_plan_entry is None  # no entry: nothing marked, not an error
    assert out.feedback is None
    assert _last_made(unique_user, recipe) == _noon(TODAY)  # moved without feedback too


def test_record_freezer_use_by(unique_user: TestUser):
    service = _service(unique_user)

    frozen = service.record(
        CookedMealCreate(
            recipe_id=_recipe(unique_user).id,
            cooked_on=TODAY,
            leftovers=CookedLeftovers(portions=3, location="freezer"),
        )
    )
    assert frozen.leftover is not None
    assert frozen.leftover.location == PantryLocation.freezer
    assert frozen.leftover.use_by == TODAY + timedelta(days=90)

    given = TODAY + timedelta(days=10)
    explicit = service.record(
        CookedMealCreate(
            recipe_id=_recipe(unique_user).id,
            cooked_on=TODAY,
            leftovers=CookedLeftovers(portions=1, location="freezer", use_by=given),
        )
    )
    assert explicit.leftover is not None and explicit.leftover.use_by == given


def test_leftover_portions_validated_by_schema():
    for portions in (0, 51):
        with pytest.raises(ValidationError):
            CookedLeftovers(portions=portions)


def test_record_refusals_write_nothing(unique_user: TestUser, h2_user: TestUser):
    service = _service(unique_user)
    food = _food(unique_user)
    recipe = _recipe(unique_user, [food])
    entry = _plan(unique_user, recipe, TODAY)
    item = _item(unique_user, food.name, food)
    unrelated = _item(unique_user, random_string(10))
    other_household_item = _item(h2_user, food.name, food)
    other_household_entry = _plan(h2_user, recipe, TODAY)
    used_up = [CookedPantryOutcome(pantry_item_id=item.id, outcome=PantryOutcome.used_up)]
    leftovers = CookedLeftovers(portions=2)

    def attempt(**changes: Any) -> CookedMealCreate:
        fields: dict[str, Any] = {
            "recipe_id": recipe.id,
            "cooked_on": TODAY,
            "pantry": used_up,
            "leftovers": leftovers,
            "feedback": CookedFeedback(verdict=FeedbackVerdict.ok),
        }
        return CookedMealCreate(**(fields | changes))

    refused: list[tuple[type[Exception], CookedMealCreate]] = [
        (FutureMadeOnError, attempt(cooked_on=TODAY + timedelta(days=2))),
        (NoEntryFound, attempt(recipe_id=uuid4())),
        (
            NoEntryFound,
            attempt(pantry=[CookedPantryOutcome(pantry_item_id=other_household_item.id, outcome="used_up")]),
        ),
        (
            PantryItemNotInRecipeError,
            attempt(pantry=[CookedPantryOutcome(pantry_item_id=unrelated.id, outcome="used_up")]),
        ),
        (PantryItemNotInRecipeError, attempt(pantry=used_up * 2)),
        (ValueError, attempt(leftovers=CookedLeftovers.model_construct(portions=0, location="fridge"))),
        (ValueError, attempt(leftovers=CookedLeftovers.model_construct(portions=51, location="fridge"))),
        (NoEntryFound, attempt(meal_plan_entry_id=other_household_entry.id)),
    ]

    before = _snapshot(unique_user, recipe, [entry.id])
    for error, data in refused:
        with pytest.raises(error):
            service.record(data)
        assert _snapshot(unique_user, recipe, [entry.id]) == before


def test_record_is_all_or_nothing(unique_user: TestUser, monkeypatch: pytest.MonkeyPatch):
    service = _service(unique_user)
    food = _food(unique_user)
    recipe = _recipe(unique_user, [food])
    entry = _plan(unique_user, recipe, TODAY)
    item = _item(unique_user, food.name, food)

    def fail(*_: Any, **__: Any) -> PantryItemOut:
        raise RuntimeError("disk full")

    monkeypatch.setattr(service, "_add_leftover", fail)
    before = _snapshot(unique_user, recipe, [entry.id])

    with pytest.raises(RuntimeError, match="disk full"):
        service.record(
            CookedMealCreate(
                recipe_id=recipe.id,
                cooked_on=TODAY,
                pantry=[CookedPantryOutcome(pantry_item_id=item.id, outcome=PantryOutcome.used_up)],
                leftovers=CookedLeftovers(portions=2),
                feedback=CookedFeedback(verdict=FeedbackVerdict.loved),
            )
        )

    assert _snapshot(unique_user, recipe, [entry.id]) == before
    assert "commit" not in unique_user.repos.session.__dict__


def test_record_twice_refused(unique_user: TestUser):
    service = _service(unique_user)
    recipe = _recipe(unique_user)
    _plan(unique_user, recipe, TODAY)
    data = CookedMealCreate(recipe_id=recipe.id, cooked_on=TODAY, leftovers=CookedLeftovers(portions=2))

    service.record(data)
    with pytest.raises(AlreadyCookedError, match=f"already recorded as cooked on {TODAY.isoformat()}"):
        service.record(data)

    leftovers = [i for i in unique_user.repos.pantry_items.ordered() if i.name == f"Leftover {recipe.name}"]
    assert len(leftovers) == 1


def test_record_back_dated_twice_refused(unique_user: TestUser):
    service = _service(unique_user)
    recipe = _recipe(unique_user)
    yesterday = TODAY - timedelta(days=1)
    _plan(unique_user, recipe, yesterday)
    data = CookedMealCreate(recipe_id=recipe.id, cooked_on=yesterday, leftovers=CookedLeftovers(portions=2))

    first = service.record(data)
    assert first.meal_plan_entry is not None
    with pytest.raises(AlreadyCookedError, match=f"already recorded as cooked on {yesterday.isoformat()}"):
        service.record(data)

    leftovers = [i for i in unique_user.repos.pantry_items.ordered() if i.name == f"Leftover {recipe.name}"]
    assert len(leftovers) == 1


def test_record_given_entry_already_done(unique_user: TestUser):
    service = _service(unique_user)
    recipe = _recipe(unique_user)
    entry = _plan(unique_user, recipe, TODAY - timedelta(days=3))
    unique_user.repos.meals.patch(entry.id, {"cooked_at": datetime.now(UTC) - timedelta(days=3)})

    with pytest.raises(AlreadyCookedError):
        service.record(CookedMealCreate(recipe_id=recipe.id, cooked_on=TODAY, meal_plan_entry_id=entry.id))


def test_record_other_household_recipe(unique_user: TestUser, h2_user: TestUser):
    food = _food(h2_user)
    recipe = _recipe(h2_user, [food])
    mine = _plan(unique_user, recipe, TODAY)
    theirs = _plan(h2_user, recipe, TODAY)
    my_item = _item(unique_user, food.name, food)
    their_item = _item(h2_user, food.name, food)

    out = _service(unique_user).record(
        CookedMealCreate(
            recipe_id=recipe.id,
            cooked_on=TODAY,
            pantry=[CookedPantryOutcome(pantry_item_id=my_item.id, outcome=PantryOutcome.used_up)],
            leftovers=CookedLeftovers(portions=1),
        )
    )

    assert out.meal_plan_entry is not None and out.meal_plan_entry.id == mine.id
    assert _entry(h2_user, theirs.id).cooked_at is None
    assert unique_user.repos.pantry_items.get_one(my_item.id) is None
    assert h2_user.repos.pantry_items.get_one(their_item.id) is not None
    assert out.leftover is not None and str(out.leftover.household_id) == str(unique_user.household_id)
    assert _last_made(unique_user, recipe) == _noon(TODAY)
    assert _last_made(h2_user, recipe) is None


def test_uncook_entry_keeps_last_made(unique_user: TestUser, h2_user: TestUser):
    service = _service(unique_user)
    recipe = _recipe(unique_user)
    entry = _plan(unique_user, recipe, TODAY)
    service.record(CookedMealCreate(recipe_id=recipe.id, cooked_on=TODAY, meal_plan_entry_id=entry.id))
    assert _entry(unique_user, entry.id).cooked_at is not None

    out = service.uncook_entry(entry.id)

    assert out.cooked_at is None
    assert _entry(unique_user, entry.id).cooked_at is None
    assert _last_made(unique_user, recipe) == _noon(TODAY)

    with pytest.raises(NoEntryFound):
        service.uncook_entry(_plan(h2_user, recipe, TODAY).id)
