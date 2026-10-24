from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _create_recipe(api_client: TestClient, user: TestUser) -> str:
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=user.token)
    assert response.status_code == 201
    slug = response.json()
    response = api_client.get(api_routes.recipes_slug(slug), headers=user.token)
    assert response.status_code == 200
    return response.json()["id"]


def _record(api_client: TestClient, user: TestUser, recipe_id: str, verdict: str, made_on: str, **extra) -> dict:
    response = api_client.post(
        api_routes.households_recipe_feedback,
        json={"recipeId": recipe_id, "verdict": verdict, "madeOn": made_on, **extra},
        headers=user.token,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_newest_first(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe_id = _create_recipe(api_client, user)

    first = _record(api_client, user, recipe_id, "ok", "2026-10-01", effort=2, note="a bit bland", forWhom="kids")
    assert first["recipeId"] == recipe_id
    assert first["verdict"] == "ok"
    assert first["effort"] == 2
    assert first["note"] == "a bit bland"
    assert first["forWhom"] == "kids"
    assert first["madeOn"] == "2026-10-01"
    assert first["householdId"] == str(user.household_id)
    assert first["userId"] == str(user.user_id)
    assert first["recipe"]["id"] == recipe_id
    second = _record(api_client, user, recipe_id, "loved", "2026-10-20")
    older = _record(api_client, user, recipe_id, "never_again", "2026-09-01")

    response = api_client.get(api_routes.households_recipe_feedback, params={"recipeId": recipe_id}, headers=user.token)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3
    assert [item["id"] for item in page["items"]] == [second["id"], first["id"], older["id"]]

    response = api_client.get(
        api_routes.households_recipe_feedback,
        params={"recipeId": recipe_id, "page": 2, "perPage": 2},
        headers=user.token,
    )
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3
    assert page["total_pages"] == 2
    assert [item["id"] for item in page["items"]] == [older["id"]]


def test_list_without_recipe_is_latest_across_recipes(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe_a = _create_recipe(api_client, user)
    recipe_b = _create_recipe(api_client, user)

    a_old = _record(api_client, user, recipe_a, "ok", "2026-10-01")
    b_new = _record(api_client, user, recipe_b, "loved", "2026-10-15")
    a_new = _record(api_client, user, recipe_a, "loved", "2026-10-10")

    response = api_client.get(api_routes.households_recipe_feedback, headers=user.token)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3
    assert [item["id"] for item in page["items"]] == [b_new["id"], a_new["id"], a_old["id"]]


def test_delete(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe_id = _create_recipe(api_client, user)
    row = _record(api_client, user, recipe_id, "loved", "2026-10-20")

    response = api_client.delete(api_routes.households_recipe_feedback_item_id(row["id"]), headers=user.token)
    assert response.status_code == 200
    assert response.json()["id"] == row["id"]

    listed = api_client.get(api_routes.households_recipe_feedback, params={"recipeId": recipe_id}, headers=user.token)
    assert listed.json()["total"] == 0

    response = api_client.delete(api_routes.households_recipe_feedback_item_id(row["id"]), headers=user.token)
    assert response.status_code == 404


def test_summary(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe_a = _create_recipe(api_client, user)
    recipe_b = _create_recipe(api_client, user)
    recipe_without = _create_recipe(api_client, user)

    _record(api_client, user, recipe_a, "loved", "2026-10-01")
    _record(api_client, user, recipe_a, "ok", "2026-10-10")
    _record(api_client, user, recipe_b, "never_again", "2026-10-05")

    response = api_client.get(
        api_routes.households_recipe_feedback_summary,
        params={"recipeIds": f"{recipe_a},{recipe_b},{recipe_without}"},
        headers=user.token,
    )
    assert response.status_code == 200
    summaries = response.json()
    assert set(summaries) == {recipe_a, recipe_b}
    assert summaries[recipe_a]["lastVerdict"] == "ok"
    assert summaries[recipe_a]["lastMadeOn"] == "2026-10-10"
    assert summaries[recipe_a]["loved"] == 1
    assert summaries[recipe_a]["ok"] == 1
    assert summaries[recipe_a]["total"] == 2
    assert summaries[recipe_b]["lastVerdict"] == "never_again"
    assert summaries[recipe_b]["neverAgain"] == 1
    assert summaries[recipe_b]["total"] == 1


def test_summary_zero_ids_is_empty(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.get(api_routes.households_recipe_feedback_summary, headers=user.token)
    assert response.status_code == 200
    assert response.json() == {}

    response = api_client.get(
        api_routes.households_recipe_feedback_summary, params={"recipeIds": ""}, headers=user.token
    )
    assert response.status_code == 200
    assert response.json() == {}


def test_summary_rejects_more_than_100_ids(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    ids = ",".join(str(uuid4()) for _ in range(101))
    response = api_client.get(
        api_routes.households_recipe_feedback_summary, params={"recipeIds": ids}, headers=user.token
    )
    assert response.status_code == 422

    ids = ",".join(str(uuid4()) for _ in range(100))
    response = api_client.get(
        api_routes.households_recipe_feedback_summary, params={"recipeIds": ids}, headers=user.token
    )
    assert response.status_code == 200
    assert response.json() == {}


def test_summary_rejects_invalid_uuid(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.get(
        api_routes.households_recipe_feedback_summary,
        params={"recipeIds": f"{uuid4()},not-a-uuid"},
        headers=user.token,
    )
    assert response.status_code == 422


def test_unknown_recipe_404(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.post(
        api_routes.households_recipe_feedback,
        json={"recipeId": str(uuid4()), "verdict": "loved"},
        headers=user.token,
    )
    assert response.status_code == 404


def test_feedback_isolated_between_households(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    recipe_id = _create_recipe(api_client, unique_user)
    row = _record(api_client, unique_user, recipe_id, "loved", "2026-10-20")

    response = api_client.delete(api_routes.households_recipe_feedback_item_id(row["id"]), headers=h2_user.token)
    assert response.status_code == 404

    for params in ({"recipeId": recipe_id}, {}):
        response = api_client.get(api_routes.households_recipe_feedback, params=params, headers=h2_user.token)
        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert response.json()["items"] == []

    response = api_client.get(
        api_routes.households_recipe_feedback_summary, params={"recipeIds": recipe_id}, headers=h2_user.token
    )
    assert response.status_code == 200
    assert response.json() == {}

    # the row survived the foreign delete attempt
    listed = api_client.get(
        api_routes.households_recipe_feedback, params={"recipeId": recipe_id}, headers=unique_user.token
    ).json()
    assert [item["id"] for item in listed["items"]] == [row["id"]]


def test_record_on_recipe_of_another_household_in_the_group(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser
):
    recipe_id = _create_recipe(api_client, unique_user)

    row = _record(api_client, h2_user, recipe_id, "loved", "2026-10-20")
    assert row["householdId"] == str(h2_user.household_id)
    assert row["userId"] == str(h2_user.user_id)
    assert row["recipe"]["id"] == recipe_id

    mine = api_client.get(api_routes.households_recipe_feedback, params={"recipeId": recipe_id}, headers=h2_user.token)
    assert [item["id"] for item in mine.json()["items"]] == [row["id"]]
    theirs = api_client.get(
        api_routes.households_recipe_feedback, params={"recipeId": recipe_id}, headers=unique_user.token
    )
    assert theirs.json()["total"] == 0


def test_record_on_recipe_of_another_group_404(api_client: TestClient, unique_user: TestUser, g2_user: TestUser):
    recipe_id = _create_recipe(api_client, g2_user)
    response = api_client.post(
        api_routes.households_recipe_feedback,
        json={"recipeId": recipe_id, "verdict": "loved"},
        headers=unique_user.token,
    )
    assert response.status_code == 404


def test_requires_auth(api_client: TestClient):
    assert api_client.get(api_routes.households_recipe_feedback).status_code == 401
    assert api_client.get(api_routes.households_recipe_feedback_summary).status_code == 401
    response = api_client.post(api_routes.households_recipe_feedback, json={"recipeId": str(uuid4()), "verdict": "ok"})
    assert response.status_code == 401
    assert api_client.delete(api_routes.households_recipe_feedback_item_id(str(uuid4()))).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"verdict": "great"},
        {"verdict": "loved", "effort": 0},
        {"verdict": "loved", "effort": 4},
        {"verdict": "loved", "madeOn": "not-a-date"},
        {},
    ],
)
def test_body_validation_422(api_client: TestClient, unique_user: TestUser, body: dict):
    recipe_id = _create_recipe(api_client, unique_user)
    response = api_client.post(
        api_routes.households_recipe_feedback, json={"recipeId": recipe_id, **body}, headers=unique_user.token
    )
    assert response.status_code == 422
