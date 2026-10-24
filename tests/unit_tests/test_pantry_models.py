from datetime import date

from mealie.repos.all_repositories import get_repositories
from mealie.schema.household.household import HouseholdCreate
from mealie.schema.household.pantry import PantryItemCreate, PantryLocation, PantrySource
from mealie.schema.recipe.recipe_ingredient import SaveIngredientFood, SaveIngredientUnit
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def test_pantry_item_round_trip(unique_user: TestUser):
    repo = unique_user.repos.pantry_items
    created = repo.create(PantryItemCreate(name="Eggs", bought_on=date(2026, 10, 24)))

    fetched = repo.get_one(created.id)
    assert fetched is not None
    assert fetched.name == "Eggs"
    assert fetched.bought_on == date(2026, 10, 24)
    assert str(fetched.household_id) == str(unique_user.household_id)
    assert str(fetched.group_id) == str(unique_user.group_id)
    assert fetched.location == PantryLocation.cupboard
    assert fetched.source == PantrySource.manual
    assert fetched.food is None
    assert fetched.unit is None


def test_ordered_puts_use_by_first_and_nulls_last(unique_user: TestUser):
    # unique_user is shared across tests, so only look at the rows created here
    tag = random_string(8)
    repo = unique_user.repos.pantry_items
    repo.create(PantryItemCreate(name=f"{tag} 26th", use_by=date(2026, 10, 26)))
    repo.create(PantryItemCreate(name=f"{tag} none", bought_on=date(2026, 10, 24)))
    repo.create(PantryItemCreate(name=f"{tag} 25th", use_by=date(2026, 10, 25)))

    names = [item.name for item in repo.ordered() if item.name.startswith(tag)]
    assert names == [f"{tag} 25th", f"{tag} 26th", f"{tag} none"]


def test_ordered_without_use_by_puts_latest_bought_first(unique_user: TestUser):
    tag = random_string(8)
    repo = unique_user.repos.pantry_items
    repo.create(PantryItemCreate(name=f"{tag} older", bought_on=date(2026, 10, 1)))
    repo.create(PantryItemCreate(name=f"{tag} undated"))
    repo.create(PantryItemCreate(name=f"{tag} newer", bought_on=date(2026, 10, 20)))

    names = [item.name for item in repo.ordered() if item.name.startswith(tag)]
    assert names == [f"{tag} newer", f"{tag} older", f"{tag} undated"]


def test_ordered_filters_by_location(unique_user: TestUser):
    tag = random_string(8)
    repo = unique_user.repos.pantry_items
    repo.create(PantryItemCreate(name=f"{tag} milk", location=PantryLocation.fridge))
    repo.create(PantryItemCreate(name=f"{tag} rice"))

    fridge = repo.ordered(PantryLocation.fridge)
    assert all(item.location == PantryLocation.fridge for item in fridge)
    assert [item.name for item in fridge if item.name.startswith(tag)] == [f"{tag} milk"]


def test_by_name_is_case_insensitive(unique_user: TestUser):
    tag = random_string(8)
    repo = unique_user.repos.pantry_items
    created = repo.create(PantryItemCreate(name=f"{tag} Crème fraîche"))

    assert [item.id for item in repo.by_name(f"{tag.upper()} crème FRAÎCHE")] == [created.id]
    assert repo.by_name(f"{tag} crème") == []


def test_pantry_items_are_scoped_to_household(unique_user: TestUser, h2_user: TestUser):
    name = random_string(12)
    created = unique_user.repos.pantry_items.create(PantryItemCreate(name=name))

    assert h2_user.repos.pantry_items.by_name(name) == []
    assert created.id not in {item.id for item in h2_user.repos.pantry_items.ordered()}
    assert h2_user.repos.pantry_items.get_one(created.id) is None


def test_by_food_returns_linked_items_with_food(unique_user: TestUser):
    food = unique_user.repos.ingredient_foods.create(
        SaveIngredientFood(name=random_string(10), group_id=unique_user.group_id)
    )
    repo = unique_user.repos.pantry_items
    linked = repo.create(PantryItemCreate(name=food.name, food_id=food.id))
    repo.create(PantryItemCreate(name=food.name))

    found = repo.by_food(food.id)
    assert [item.id for item in found] == [linked.id]
    assert found[0].food is not None
    assert found[0].food.id == food.id
    # by_name only matches free-text rows (no linked food)
    assert [item.food_id for item in repo.by_name(food.name)] == [None]


def test_merging_foods_and_units_repoints_pantry_items(unique_user: TestUser):
    foods = unique_user.repos.ingredient_foods
    units = unique_user.repos.ingredient_units
    from_food, to_food = (
        foods.create(SaveIngredientFood(name=random_string(10), group_id=unique_user.group_id)) for _ in range(2)
    )
    from_unit, to_unit = (
        units.create(SaveIngredientUnit(name=random_string(10), group_id=unique_user.group_id)) for _ in range(2)
    )
    repo = unique_user.repos.pantry_items
    item = repo.create(PantryItemCreate(name=from_food.name, food_id=from_food.id, quantity=2, unit_id=from_unit.id))

    foods.merge(from_food.id, to_food.id)
    units.merge(from_unit.id, to_unit.id)

    repo.session.expire_all()
    fetched = repo.get_one(item.id)
    assert fetched is not None
    assert fetched.food_id == to_food.id
    assert fetched.unit_id == to_unit.id


def test_deleting_household_deletes_its_pantry_items(unique_user: TestUser):
    session = unique_user.repos.session
    group_repos = get_repositories(session, group_id=unique_user.group_id, household_id=None)
    household = group_repos.households.create(HouseholdCreate(group_id=unique_user.group_id, name=random_string()))
    pantry = get_repositories(session, group_id=unique_user.group_id, household_id=household.id).pantry_items
    item = pantry.create(PantryItemCreate(name="Eggs"))

    group_repos.households.delete(household.id)

    assert get_repositories(session, group_id=None, household_id=None).pantry_items.get_one(item.id) is None
