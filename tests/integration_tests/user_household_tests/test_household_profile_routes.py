from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _create(api_client: TestClient, user: TestUser, **data) -> dict:
    response = api_client.post(api_routes.households_profile_members, json=data, headers=user.token)
    assert response.status_code == 201, response.text
    return response.json()


def _profile(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.get(api_routes.households_profile, headers=user.token)
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_profile(api_client: TestClient, unique_user_fn_scoped: TestUser):
    assert _profile(api_client, unique_user_fn_scoped) == {"members": [], "preferences": None}


def test_member_crud(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    sam = _create(
        api_client,
        user,
        name="  Sam ",
        userId=str(user.user_id),
        isChild=False,
        diet="vegetarian",
        allergies=["Peanuts", " peanuts ", ""],
        likes=["pasta"],
        notes="no spice",
        position=1,
    )
    assert sam["name"] == "Sam"
    assert sam["userId"] == str(user.user_id)
    assert sam["householdId"] == str(user.household_id)
    assert sam["groupId"] == str(user.group_id)
    assert sam["diet"] == "vegetarian"
    assert sam["allergies"] == ["Peanuts"]
    assert sam["likes"] == ["pasta"]
    kid = _create(api_client, user, name="Kid", isChild=True)
    assert kid["position"] == 0

    profile = _profile(api_client, user)
    assert [m["id"] for m in profile["members"]] == [kid["id"], sam["id"]]
    assert profile["preferences"] is None

    # partial update: only the fields sent change
    response = api_client.put(
        api_routes.households_profile_members_item_id(sam["id"]),
        json={"dislikes": ["mushrooms"], "notes": None},
        headers=user.token,
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["dislikes"] == ["mushrooms"]
    assert updated["notes"] is None
    assert updated["allergies"] == ["Peanuts"]
    assert updated["likes"] == ["pasta"]
    assert updated["diet"] == "vegetarian"
    assert updated["userId"] == str(user.user_id)

    response = api_client.delete(api_routes.households_profile_members_item_id(sam["id"]), headers=user.token)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == sam["id"]
    assert [m["id"] for m in _profile(api_client, user)["members"]] == [kid["id"]]

    response = api_client.delete(api_routes.households_profile_members_item_id(sam["id"]), headers=user.token)
    assert response.status_code == 404


def test_duplicate_name_is_a_conflict(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _create(api_client, user, name="Sam")
    other = _create(api_client, user, name="Alex")

    response = api_client.post(api_routes.households_profile_members, json={"name": "SAM"}, headers=user.token)
    assert response.status_code == 409
    assert "Sam" in response.json()["detail"]["message"]

    response = api_client.put(
        api_routes.households_profile_members_item_id(other["id"]), json={"name": " sam"}, headers=user.token
    )
    assert response.status_code == 409
    assert [m["name"] for m in _profile(api_client, user)["members"]] == ["Alex", "Sam"]


def test_second_profile_for_a_user_is_a_conflict(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _create(api_client, user, name="Me", userId=str(user.user_id))
    other = _create(api_client, user, name="Someone")

    response = api_client.post(
        api_routes.households_profile_members,
        json={"name": "Me again", "userId": str(user.user_id)},
        headers=user.token,
    )
    assert response.status_code == 409
    assert "already linked" in response.json()["detail"]["message"]

    response = api_client.put(
        api_routes.households_profile_members_item_id(other["id"]),
        json={"userId": str(user.user_id)},
        headers=user.token,
    )
    assert response.status_code == 409


def test_linking_a_user_outside_the_household_is_not_found(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, g2_user: TestUser
):
    member = _create(api_client, unique_user, name=f"Member {random_string(8)}")
    for outsider in (h2_user.user_id, g2_user.user_id, uuid4()):
        response = api_client.post(
            api_routes.households_profile_members,
            json={"name": random_string(), "userId": str(outsider)},
            headers=unique_user.token,
        )
        assert response.status_code == 404
        response = api_client.put(
            api_routes.households_profile_members_item_id(member["id"]),
            json={"userId": str(outsider)},
            headers=unique_user.token,
        )
        assert response.status_code == 404


def test_other_households_cannot_see_or_change_members(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, g2_user: TestUser
):
    name = f"Secret {random_string(8)}"
    mine = _create(api_client, unique_user, name=name, likes=["pasta"])

    for other in (h2_user, g2_user):
        assert mine["id"] not in {m["id"] for m in _profile(api_client, other)["members"]}
        response = api_client.put(
            api_routes.households_profile_members_item_id(mine["id"]), json={"likes": ["soup"]}, headers=other.token
        )
        assert response.status_code == 404
        response = api_client.delete(api_routes.households_profile_members_item_id(mine["id"]), headers=other.token)
        assert response.status_code == 404
        # the same name is free in another household
        response = api_client.post(api_routes.households_profile_members, json={"name": name}, headers=other.token)
        assert response.status_code == 201
        api_client.delete(api_routes.households_profile_members_item_id(response.json()["id"]), headers=other.token)

    still = next(m for m in _profile(api_client, unique_user)["members"] if m["id"] == mine["id"])
    assert still["likes"] == ["pasta"]


def test_unknown_member_is_not_found(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    item = api_routes.households_profile_members_item_id(uuid4())
    assert api_client.put(item, json={"notes": "x"}, headers=user.token).status_code == 404
    assert api_client.delete(item, headers=user.token).status_code == 404


def test_requires_a_token(api_client: TestClient):
    item = api_routes.households_profile_members_item_id(uuid4())
    assert api_client.get(api_routes.households_profile).status_code == 401
    assert api_client.post(api_routes.households_profile_members, json={"name": "x"}).status_code == 401
    assert api_client.put(item, json={"notes": "x"}).status_code == 401
    assert api_client.delete(item).status_code == 401
    assert api_client.put(api_routes.households_profile_preferences, json={}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": "   "},
        {"name": "x", "diet": "carnivore"},
        {"name": "x", "position": -1},
        {"name": "x", "allergies": ["a" * 61]},
        {"name": "x", "likes": [f"item {i}" for i in range(31)]},
        {"name": "x", "notes": "n" * 2001},
        {"name": "x", "userId": "not-a-uuid"},
    ],
)
def test_create_validation(api_client: TestClient, unique_user_fn_scoped: TestUser, body: dict):
    response = api_client.post(api_routes.households_profile_members, json=body, headers=unique_user_fn_scoped.token)
    assert response.status_code == 422, response.text
    assert _profile(api_client, unique_user_fn_scoped)["members"] == []


def test_update_validation(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    member = _create(api_client, user, name="Sam", likes=["pasta"])
    item = api_routes.households_profile_members_item_id(member["id"])
    for body in ({"name": ""}, {"likes": None}, {"diet": "carnivore"}, {"position": -2}):
        response = api_client.put(item, json=body, headers=user.token)
        assert response.status_code == 422, body
    assert (
        api_client.put(api_routes.households_profile_members_item_id("nope"), json={}, headers=user.token).status_code
        == 422
    )
    assert _profile(api_client, user)["members"][0]["likes"] == ["pasta"]


def test_preferences_upsert(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.put(
        api_routes.households_profile_preferences,
        json={"defaultServings": 4, "quickWeekdays": [3, 0, 3], "favouriteCuisines": ["Thai", "thai", "Italian"]},
        headers=user.token,
    )
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["defaultServings"] == 4
    assert created["quickWeekdays"] == [0, 3]
    assert created["favouriteCuisines"] == ["Thai", "Italian"]
    assert created["householdId"] == str(user.household_id)

    # partial update: same row, only the fields sent change
    response = api_client.put(
        api_routes.households_profile_preferences,
        json={"weeknightMaxMinutes": 30, "defaultServings": None},
        headers=user.token,
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["weeknightMaxMinutes"] == 30
    assert updated["defaultServings"] is None
    assert updated["quickWeekdays"] == [0, 3]
    assert updated["favouriteCuisines"] == ["Thai", "Italian"]

    assert _profile(api_client, user)["preferences"] == updated

    for body in ({"defaultServings": 0}, {"quickWeekdays": [7]}, {"weekendMaxMinutes": 1000}):
        response = api_client.put(api_routes.households_profile_preferences, json=body, headers=user.token)
        assert response.status_code == 422, body
    assert _profile(api_client, user)["preferences"] == updated
