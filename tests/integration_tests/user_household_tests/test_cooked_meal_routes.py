from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

# the cooking date is refused when later than the server's tomorrow: use the real today
TODAY = datetime.now().astimezone().date()


def _create_recipe(api_client: TestClient, user: TestUser, ingredient_food: str | None = None) -> dict:
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=user.token)
    assert response.status_code == 201
    slug = response.json()
    recipe = api_client.get(api_routes.recipes_slug(slug), headers=user.token).json()
    if ingredient_food:
        food = api_client.post(api_routes.foods, json={"name": ingredient_food}, headers=user.token)
        assert food.status_code == 201, food.text
        recipe["recipeIngredient"] = [{"note": "", "quantity": 1, "food": food.json()}]
        response = api_client.put(api_routes.recipes_slug(slug), json=recipe, headers=user.token)
        assert response.status_code == 200, response.text
        recipe = api_client.get(api_routes.recipes_slug(slug), headers=user.token).json()
    return recipe


def _plan(api_client: TestClient, user: TestUser, day: date, recipe_id: str | None = None, title: str = "") -> dict:
    payload: dict = {"date": day.isoformat(), "entryType": "dinner", "title": title, "text": ""}
    if recipe_id:
        payload["recipeId"] = recipe_id
    response = api_client.post(api_routes.households_mealplans, json=payload, headers=user.token)
    assert response.status_code == 201, response.text
    return response.json()


def _pantry(api_client: TestClient, user: TestUser, name: str, **extra) -> dict:
    response = api_client.post(api_routes.households_pantry, json={"name": name, **extra}, headers=user.token)
    assert response.status_code == 201, response.text
    return response.json()


def test_pantry_check(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    food = random_string()
    recipe = _create_recipe(api_client, user, food)
    entry = _plan(api_client, user, TODAY, recipe["id"])
    item = _pantry(api_client, user, food)

    response = api_client.get(
        api_routes.households_cooking_recipe_id_pantry_check(recipe["id"]),
        params={"cooked_on": TODAY.isoformat()},
        headers=user.token,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [i["id"] for i in body["items"]] == [item["id"]]
    assert body["mealPlanEntryId"] == entry["id"]
    assert body["suggestedLeftoverPortions"] == 0

    response = api_client.get(
        api_routes.households_cooking_recipe_id_pantry_check(recipe["id"]),
        params={"cooked_on": TODAY.isoformat(), "scale": 2},
        headers=user.token,
    )
    assert response.status_code == 200


def test_pantry_check_recipe_outside_group_is_404(api_client: TestClient, unique_user_fn_scoped: TestUser):
    response = api_client.get(
        api_routes.households_cooking_recipe_id_pantry_check(str(uuid4())),
        params={"cooked_on": TODAY.isoformat()},
        headers=unique_user_fn_scoped.token,
    )
    assert response.status_code == 404


def test_record_and_conflict(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    food = random_string()
    recipe = _create_recipe(api_client, user, food)
    entry = _plan(api_client, user, TODAY, recipe["id"])
    item = _pantry(api_client, user, food)
    payload = {
        "recipeId": recipe["id"],
        "cookedOn": TODAY.isoformat(),
        "pantry": [{"pantryItemId": item["id"], "outcome": "used_up"}],
        "leftovers": {"portions": 2},
        "feedback": {"verdict": "loved"},
    }

    response = api_client.post(api_routes.households_cooking, json=payload, headers=user.token)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mealPlanEntry"]["id"] == entry["id"]
    assert body["mealPlanEntry"]["cookedAt"] is not None
    assert body["removedItemIds"] == [item["id"]]
    assert body["leftover"]["name"] == f"Leftover {recipe['name']}"
    assert body["leftover"]["source"] == "leftover"
    assert body["feedback"]["verdict"] == "loved"

    response = api_client.post(api_routes.households_cooking, json=payload, headers=user.token)
    assert response.status_code == 409
    assert f"already recorded as cooked on {TODAY.isoformat()}" in response.text


def test_record_pantry_item_not_in_recipe_is_400(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user, random_string())
    stranger = _pantry(api_client, user, random_string())

    response = api_client.post(
        api_routes.households_cooking,
        json={
            "recipeId": recipe["id"],
            "cookedOn": TODAY.isoformat(),
            "pantry": [{"pantryItemId": stranger["id"], "outcome": "used_up"}],
        },
        headers=user.token,
    )
    assert response.status_code == 400
    assert "pantry items not in this recipe" in response.text
    assert api_client.get(api_routes.households_pantry_item_id(stranger["id"]), headers=user.token).status_code == 200


def test_record_future_date_is_400(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    response = api_client.post(
        api_routes.households_cooking,
        json={"recipeId": recipe["id"], "cookedOn": (TODAY + timedelta(days=5)).isoformat()},
        headers=user.token,
    )
    assert response.status_code == 400


def test_mark_and_unmark_recipe_entry(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    entry = _plan(api_client, user, TODAY, recipe["id"])

    response = api_client.post(
        api_routes.households_mealplans_item_id_cooked(entry["id"]),
        params={"cooked_on": TODAY.isoformat()},
        headers=user.token,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mealPlanEntry"]["id"] == entry["id"]
    assert body["mealPlanEntry"]["cookedAt"] is not None
    assert body["leftover"] is None and body["keptItems"] == [] and body["removedItemIds"] == []

    response = api_client.post(
        api_routes.households_mealplans_item_id_cooked(entry["id"]),
        params={"cooked_on": TODAY.isoformat()},
        headers=user.token,
    )
    assert response.status_code == 409

    response = api_client.delete(api_routes.households_mealplans_item_id_cooked(entry["id"]), headers=user.token)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == entry["id"]
    assert response.json()["cookedAt"] is None


def test_mark_title_only_entry(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    entry = _plan(api_client, user, TODAY, title="Takeaway")

    response = api_client.post(
        api_routes.households_mealplans_item_id_cooked(entry["id"]),
        params={"cooked_on": TODAY.isoformat()},
        headers=user.token,
    )
    assert response.status_code == 200, response.text
    assert response.json()["mealPlanEntry"]["cookedAt"] is not None
    assert response.json()["feedback"] is None

    # nothing was recorded as made: no recipe, so no last made and no timeline event to look at
    page = api_client.get(api_routes.households_recipe_feedback, headers=user.token).json()
    assert page["total"] == 0


def test_entry_of_another_household_is_404(api_client: TestClient, unique_user_fn_scoped: TestUser, h2_user: TestUser):
    theirs = _plan(api_client, h2_user, TODAY, title="Theirs")

    response = api_client.post(
        api_routes.households_mealplans_item_id_cooked(theirs["id"]),
        params={"cooked_on": TODAY.isoformat()},
        headers=unique_user_fn_scoped.token,
    )
    assert response.status_code == 404
    response = api_client.delete(
        api_routes.households_mealplans_item_id_cooked(theirs["id"]), headers=unique_user_fn_scoped.token
    )
    assert response.status_code == 404
