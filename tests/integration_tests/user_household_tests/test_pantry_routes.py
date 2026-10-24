from uuid import uuid4

from fastapi.testclient import TestClient

from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _create_list(api_client: TestClient, user: TestUser) -> str:
    response = api_client.post(api_routes.households_shopping_lists, json={"name": random_string()}, headers=user.token)
    assert response.status_code == 201
    return response.json()["id"]


def _add_list_item(api_client: TestClient, user: TestUser, list_id: str, note: str, checked: bool) -> str:
    response = api_client.post(
        api_routes.households_shopping_items,
        json={"shoppingListId": list_id, "note": note, "quantity": 1, "checked": checked},
        headers=user.token,
    )
    assert response.status_code == 201
    return response.json()["createdItems"][0]["id"]


def test_create_and_list(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    later = {"name": "Yoghurt", "location": "fridge", "useBy": "2026-11-10"}
    sooner = {"name": "Milk", "location": "fridge", "useBy": "2026-10-26"}
    no_date = {"name": "Rice", "location": "cupboard"}

    created_ids = []
    for payload in (later, no_date, sooner):
        response = api_client.post(api_routes.households_pantry, json=payload, headers=user.token)
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == payload["name"]
        assert body["householdId"] == str(user.household_id)
        created_ids.append(body["id"])

    response = api_client.get(api_routes.households_pantry, headers=user.token)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3
    # default order: use_by ascending, nulls last
    assert [item["name"] for item in page["items"]] == ["Milk", "Yoghurt", "Rice"]

    response = api_client.get(api_routes.households_pantry, params={"location": "fridge"}, headers=user.token)
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["Milk", "Yoghurt"]

    # pagination slices the ordered list
    response = api_client.get(api_routes.households_pantry, params={"page": 2, "perPage": 2}, headers=user.token)
    page = response.json()
    assert page["total"] == 3
    assert page["total_pages"] == 2
    assert [item["name"] for item in page["items"]] == ["Rice"]

    # an explicit orderBy goes through the generic paginator
    response = api_client.get(
        api_routes.households_pantry,
        params={"orderBy": "name", "orderDirection": "desc", "location": "fridge"},
        headers=user.token,
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["Yoghurt", "Milk"]

    # a query filter without orderBy keeps the default order
    response = api_client.get(
        api_routes.households_pantry, params={"queryFilter": 'name <> "Milk"'}, headers=user.token
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["Yoghurt", "Rice"]


def test_create_merge_returns_200(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.post(api_routes.households_pantry, json={"name": "Flour", "quantity": 1}, headers=user.token)
    assert response.status_code == 201
    first_id = response.json()["id"]

    response = api_client.post(api_routes.households_pantry, json={"name": "flour", "quantity": 2}, headers=user.token)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == first_id
    assert body["quantity"] == 3

    response = api_client.get(api_routes.households_pantry, headers=user.token)
    assert response.json()["total"] == 1


def test_update_and_delete(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.post(api_routes.households_pantry, json={"name": "Butter"}, headers=user.token)
    item = response.json()

    response = api_client.get(api_routes.households_pantry_item_id(item["id"]), headers=user.token)
    assert response.status_code == 200
    assert response.json()["name"] == "Butter"

    response = api_client.put(
        api_routes.households_pantry_item_id(item["id"]),
        json={"name": "Butter", "location": "fridge", "openedOn": "2026-10-20"},
        headers=user.token,
    )
    assert response.status_code == 200
    assert response.json()["location"] == "fridge"
    assert response.json()["openedOn"] == "2026-10-20"

    response = api_client.delete(api_routes.households_pantry_item_id(item["id"]), headers=user.token)
    assert response.status_code == 200
    assert response.json()["id"] == item["id"]

    for method in (api_client.get, api_client.delete):
        response = method(api_routes.households_pantry_item_id(item["id"]), headers=user.token)
        assert response.status_code == 404
    response = api_client.put(
        api_routes.households_pantry_item_id(item["id"]), json={"name": "Butter"}, headers=user.token
    )
    assert response.status_code == 404


def test_put_away_route(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    list_id = _create_list(api_client, user)
    checked_ids = [_add_list_item(api_client, user, list_id, note, checked=True) for note in ("Apples", "Pasta")]
    unchecked_id = _add_list_item(api_client, user, list_id, "Coffee", checked=False)

    response = api_client.post(
        api_routes.households_shopping_lists_list_id_put_away(list_id), json={"itemIds": None}, headers=user.token
    )
    assert response.status_code == 200
    result = response.json()
    assert sorted(item["name"] for item in result["created"]) == ["Apples", "Pasta"]
    assert result["merged"] == []
    assert sorted(result["removedItemIds"]) == sorted(checked_ids)

    response = api_client.get(api_routes.households_shopping_lists_item_id(list_id), headers=user.token)
    assert [item["id"] for item in response.json()["listItems"]] == [unchecked_id]

    response = api_client.get(api_routes.households_pantry, headers=user.token)
    assert sorted(item["name"] for item in response.json()["items"]) == ["Apples", "Pasta"]


def test_put_away_unchecked_ids_422(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    list_id = _create_list(api_client, user)
    checked_id = _add_list_item(api_client, user, list_id, "Eggs", checked=True)
    unchecked_id = _add_list_item(api_client, user, list_id, "Bread", checked=False)

    response = api_client.post(
        api_routes.households_shopping_lists_list_id_put_away(list_id),
        json={"itemIds": [checked_id, unchecked_id]},
        headers=user.token,
    )
    assert response.status_code == 422
    assert unchecked_id in response.json()["detail"]["message"]
    assert checked_id not in response.json()["detail"]["message"]

    # nothing moved, nothing deleted
    response = api_client.get(api_routes.households_shopping_lists_item_id(list_id), headers=user.token)
    assert len(response.json()["listItems"]) == 2
    response = api_client.get(api_routes.households_pantry, headers=user.token)
    assert response.json()["total"] == 0


def test_put_away_foreign_list_404(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    list_id = _create_list(api_client, unique_user)
    item_id = _add_list_item(api_client, unique_user, list_id, "Cheese", checked=True)

    response = api_client.post(
        api_routes.households_shopping_lists_list_id_put_away(list_id), json={"itemIds": None}, headers=h2_user.token
    )
    assert response.status_code == 404

    response = api_client.post(
        api_routes.households_shopping_lists_list_id_put_away(uuid4()),
        json={"itemIds": None},
        headers=unique_user.token,
    )
    assert response.status_code == 404

    # an item id that is not on the list is a 404 too
    response = api_client.post(
        api_routes.households_shopping_lists_list_id_put_away(list_id),
        json={"itemIds": [str(uuid4())]},
        headers=unique_user.token,
    )
    assert response.status_code == 404

    response = api_client.get(api_routes.households_shopping_lists_item_id(list_id), headers=unique_user.token)
    assert [item["id"] for item in response.json()["listItems"]] == [item_id]


def test_pantry_isolated_between_households(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    response = api_client.post(api_routes.households_pantry, json={"name": random_string()}, headers=unique_user.token)
    assert response.status_code == 201
    item_id = response.json()["id"]

    item_route = api_routes.households_pantry_item_id(item_id)
    assert api_client.get(item_route, headers=h2_user.token).status_code == 404
    assert api_client.put(item_route, json={"name": "stolen"}, headers=h2_user.token).status_code == 404
    assert api_client.delete(item_route, headers=h2_user.token).status_code == 404

    listed = api_client.get(api_routes.households_pantry, params={"perPage": -1}, headers=h2_user.token).json()
    assert item_id not in [item["id"] for item in listed["items"]]

    assert api_client.get(item_route, headers=unique_user.token).status_code == 200
