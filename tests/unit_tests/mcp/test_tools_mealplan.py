import contextlib
from datetime import date, datetime, timedelta

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError
from mealie.mcp.tools.mealplan import (
    MealplanEntryIn,
    add_mealplan_entries,
    get_mealplan,
    get_recent_meals,
    remove_mealplan_entry,
)
from mealie.schema.meal_plan.new_meal import PlanEntryType, SavePlanEntry
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _today() -> date:
    return datetime.now().astimezone().date()


SCOPES = ["recipes:read", "mealplan:write"]


def _as_user(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, scopes: list[str] = SCOPES) -> None:
    token = AccessToken(token="t", client_id="c", scopes=scopes, subject=str(user.user_id))
    monkeypatch.setattr(context, "get_access_token", lambda: token)
    monkeypatch.setattr(auth, "get_access_token", lambda: token)
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))


def _create_recipe(api_client: TestClient, user: TestUser, **updates) -> str:
    response = api_client.post(api_routes.recipes, json={"name": random_string(12)}, headers=user.token)
    assert response.status_code == 201
    slug = response.json()
    if updates:
        body = api_client.get(api_routes.recipes_slug(slug), headers=user.token).json()
        body.update(updates)
        response = api_client.put(api_routes.recipes_slug(slug), json=body, headers=user.token)
        assert response.status_code == 200, response.text
    return slug


@pytest.mark.asyncio
async def test_add_entries_with_slug_and_free_text(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    slug = _create_recipe(api_client, unique_user)
    _as_user(monkeypatch, session, unique_user)
    day = _today() + timedelta(days=400)

    result = await add_mealplan_entries(
        [
            MealplanEntryIn(date=day, recipe_slug=slug),
            MealplanEntryIn(date=day, entry_type=PlanEntryType.lunch, title="Leftovers", text="from monday"),
        ]
    )

    assert len(result["created"]) == 2
    assert result["created"][0]["recipe"]["slug"] == slug
    assert result["created"][0]["entry_type"] == "dinner"
    assert result["created"][1]["title"] == "Leftovers"
    assert result["created"][1]["recipe"] is None
    assert result["mealplan_url"].endswith("/household/mealplan/planner/view")

    planned = await get_mealplan(day, day)
    assert {e["id"] for e in planned["entries"]} == {e["id"] for e in result["created"]}


@pytest.mark.asyncio
async def test_add_entries_unknown_slug_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    slug = _create_recipe(api_client, unique_user)
    _as_user(monkeypatch, session, unique_user)
    day = _today() + timedelta(days=500)

    with pytest.raises(McpToolError, match="recipe not found: nope-nope"):
        await add_mealplan_entries(
            [MealplanEntryIn(date=day, recipe_slug=slug), MealplanEntryIn(date=day, recipe_slug="nope-nope")]
        )

    assert (await get_mealplan(day, day))["entries"] == []


@pytest.mark.asyncio
async def test_servings_computes_scale(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    slug = _create_recipe(api_client, unique_user, recipeServings=4)
    _as_user(monkeypatch, session, unique_user)
    day = _today() + timedelta(days=600)

    result = await add_mealplan_entries([MealplanEntryIn(date=day, recipe_slug=slug, servings=2)])

    entry_id = result["created"][0]["id"]
    assert unique_user.repos.meals.get_one(entry_id).recipe_scale == 0.5
    assert result["created"][0]["servings"] == 2


@pytest.mark.asyncio
async def test_get_recent_meals_counts(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    slug = _create_recipe(api_client, unique_user)
    _as_user(monkeypatch, session, unique_user)
    today = _today()
    for offset in (1, 3):
        unique_user.repos.meals.create(
            SavePlanEntry(
                date=today - timedelta(days=offset),
                entry_type=PlanEntryType.dinner,
                recipe_id=unique_user.repos.recipes.get_one(slug, "slug").id,
                group_id=unique_user.group_id,
                user_id=unique_user.user_id,
            )
        )

    result = await get_recent_meals(days=7)

    dates = [e["date"] for e in result["entries"]]
    assert dates == sorted(dates, reverse=True)
    assert result["recipe_counts"][slug] == 2


@pytest.mark.asyncio
async def test_remove_entry_other_household_not_found(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, h2_user: TestUser
):
    other = h2_user.repos.meals.create(
        SavePlanEntry(
            date=_today(),
            entry_type=PlanEntryType.dinner,
            title="not yours",
            group_id=h2_user.group_id,
            user_id=h2_user.user_id,
        )
    )
    _as_user(monkeypatch, session, unique_user)

    with pytest.raises(McpToolError, match="mealplan_entry not found"):
        await remove_mealplan_entry(other.id)
    assert h2_user.repos.meals.get_one(other.id) is not None

    own = await add_mealplan_entries([MealplanEntryIn(date=_today(), title="mine")])
    removed = await remove_mealplan_entry(own["created"][0]["id"])
    assert removed == {"removed": own["created"][0]["id"]}
