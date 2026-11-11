from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

TONIGHT = "/api/households/trmnl/tonight"
# the service uses the server's clock; tomorrow's dinner is the next meal whatever the hour
TOMORROW = datetime.now().astimezone().date() + timedelta(days=1)


def _plan_dinner(api_client: TestClient, user: TestUser, day: date) -> dict:
    response = api_client.post("/api/recipes", json={"name": random_string()}, headers=user.token)
    assert response.status_code == 201, response.text
    recipe = api_client.get(f"/api/recipes/{response.json()}", headers=user.token).json()
    payload = {"date": day.isoformat(), "entryType": "dinner", "title": "", "text": "", "recipeId": recipe["id"]}
    response = api_client.post("/api/households/mealplans", json=payload, headers=user.token)
    assert response.status_code == 201, response.text
    return recipe


def test_tonight_requires_auth(api_client: TestClient):
    assert api_client.get(TONIGHT).status_code == 401


def test_tonight_shape(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe = _plan_dinner(api_client, user, TOMORROW)

    response = api_client.get(TONIGHT, headers=user.token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "planned"
    assert body["recipe"]["name"] == recipe["name"]
    for key in ("kicker", "generatedAt", "toBuy", "toBuyMore", "atHome", "ingredientCount", "toCheckCount", "useSoon"):
        assert key in body


def test_tonight_other_household_not_visible(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    # same group, another household
    recipe = _plan_dinner(api_client, unique_user, TOMORROW)
    assert api_client.get(TONIGHT, headers=unique_user.token).json()["state"] == "planned"

    response = api_client.get(TONIGHT, headers=h2_user.token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["recipe"] or {}).get("name") != recipe["name"]
