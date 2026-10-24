import contextlib
from datetime import date, datetime, timedelta

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError
from mealie.mcp.tools.shopping import (
    add_shopping_items,
    check_shopping_items,
    create_shopping_list_from_mealplan,
    get_shopping_list,
)
from mealie.schema.household.group_shopping_list import ShoppingListItemCreate, ShoppingListSave
from mealie.schema.meal_plan.new_meal import PlanEntryType, SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import RecipeIngredient, SaveIngredientFood
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

SCOPES = ["recipes:read", "shopping:write"]


def _as_user(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser) -> None:
    token = AccessToken(token="t", client_id="c", scopes=SCOPES, subject=str(user.user_id))
    monkeypatch.setattr(context, "get_access_token", lambda: token)
    monkeypatch.setattr(auth, "get_access_token", lambda: token)
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))


def _recipe_with_ingredients(api_client: TestClient, user: TestUser) -> str:
    response = api_client.post(api_routes.recipes, json={"name": random_string(12)}, headers=user.token)
    assert response.status_code == 201
    slug = response.json()
    body = api_client.get(api_routes.recipes_slug(slug), headers=user.token).json()
    body["recipeIngredient"] = [{"note": "2 eggs"}, {"note": "flour"}]
    response = api_client.put(api_routes.recipes_slug(slug), json=body, headers=user.token)
    assert response.status_code == 200, response.text
    return slug


def _plan(user: TestUser, day: date, slug: str | None = None, title: str = "") -> None:
    recipe_id = None
    if slug:
        recipe_id = user.repos.recipes.get_one(slug, "slug").id
    user.repos.meals.create(
        SavePlanEntry(
            date=day,
            entry_type=PlanEntryType.dinner,
            title=title,
            recipe_id=recipe_id,
            group_id=user.group_id,
            user_id=user.user_id,
        )
    )


@pytest.mark.asyncio
async def test_create_list_from_mealplan_adds_recipe_ingredients(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    slug = _recipe_with_ingredients(api_client, unique_user)
    day = datetime.now().astimezone().date() + timedelta(days=500)
    _plan(unique_user, day, slug)
    _plan(unique_user, day, title="Takeaway")
    _as_user(monkeypatch, session, unique_user)

    result = await create_shopping_list_from_mealplan(day, day)

    assert result["name"] == f"Shopping {day}–{day}"
    assert len(result["items"]) == 2
    assert {r["recipe_slug"] for r in result["recipe_references"]} == {slug}
    assert result["recipes_added"] == [slug]
    assert result["entries_without_recipe"] == ["Takeaway"]
    assert result["skipped_from_pantry"] == []
    assert result["url"].endswith(f"/shopping-lists/{result['id']}")


@pytest.mark.asyncio
async def test_create_list_reports_on_hand_foods_as_skipped(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser
):
    repos = unique_user.repos
    household = repos.households.get_by_slug_or_id(unique_user.household_id)
    assert household
    on_hand = repos.ingredient_foods.create(
        SaveIngredientFood(
            name=random_string(10), group_id=unique_user.group_id, households_with_ingredient_food=[household.slug]
        )
    )
    other = repos.ingredient_foods.create(SaveIngredientFood(name=random_string(10), group_id=unique_user.group_id))
    recipe = repos.recipes.create(
        Recipe(
            name=random_string(10),
            user_id=unique_user.user_id,
            group_id=unique_user.group_id,
            recipe_ingredient=[
                RecipeIngredient(note="", food=on_hand, quantity=1),
                RecipeIngredient(note="", food=other, quantity=1),
            ],
        )
    )
    day = datetime.now().astimezone().date() + timedelta(days=502)
    _plan(unique_user, day, recipe.slug)
    _plan(unique_user, day, recipe.slug)  # planned twice: still reported once
    _as_user(monkeypatch, session, unique_user)

    result = await create_shopping_list_from_mealplan(day, day)

    assert result["skipped_from_pantry"] == [on_hand.name]
    assert [i["food"] for i in result["items"]] == [other.name]


@pytest.mark.asyncio
async def test_reuse_existing_list_merges(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser, shopping_list
):
    slug = _recipe_with_ingredients(api_client, unique_user)
    day = datetime.now().astimezone().date() + timedelta(days=501)
    _plan(unique_user, day, slug)
    _as_user(monkeypatch, session, unique_user)

    first = await create_shopping_list_from_mealplan(day, day, list_id=str(shopping_list.id))
    second = await create_shopping_list_from_mealplan(day, day, list_id=str(shopping_list.id))

    assert first["id"] == second["id"] == str(shopping_list.id)
    assert len(second["items"]) == 2
    assert second["recipe_references"][0]["quantity"] == 2


@pytest.mark.asyncio
async def test_add_and_check_items(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, shopping_list
):
    _as_user(monkeypatch, session, unique_user)
    lid = str(shopping_list.id)

    result = await add_shopping_items(lid, ["2 lemons", "bin bags"])
    assert {i["note"] for i in result["items"]} == {"2 lemons", "bin bags"}
    assert all(not i["checked"] for i in result["items"])

    target = result["items"][0]["id"]
    checked = await check_shopping_items(lid, [target])
    assert {i["id"]: i["checked"] for i in checked["items"]}[target] is True
    unchecked = await check_shopping_items(lid, [target], checked=False)
    assert not any(i["checked"] for i in unchecked["items"])

    with pytest.raises(McpToolError):
        await check_shopping_items(lid, ["00000000-0000-0000-0000-000000000000"])
    with pytest.raises(McpToolError):
        await add_shopping_items("00000000-0000-0000-0000-000000000000", ["x"])


@pytest.mark.asyncio
async def test_get_default_list_is_most_recent(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, shopping_lists
):
    _as_user(monkeypatch, session, unique_user)
    older, newer = shopping_lists[0], shopping_lists[1]
    await add_shopping_items(str(newer.id), ["touch"])  # bumps updated_at
    result = await get_shopping_list()
    assert result["id"] == str(newer.id)
    explicit = await get_shopping_list(str(older.id))
    assert explicit["id"] == str(older.id)


def _h2_list_with_item(h2_user: TestUser):
    other = h2_user.repos.group_shopping_lists.create(
        ShoppingListSave(name=random_string(8), group_id=h2_user.group_id, user_id=h2_user.user_id)
    )
    item = h2_user.repos.group_shopping_list_item.create(
        ShoppingListItemCreate(shopping_list_id=other.id, note="secret", is_food=False)
    )
    return other, item


@pytest.mark.asyncio
async def test_other_household_list_is_not_accessible(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, h2_user: TestUser, shopping_list
):
    other, item = _h2_list_with_item(h2_user)
    _as_user(monkeypatch, session, unique_user)

    with pytest.raises(McpToolError):
        await get_shopping_list(str(other.id))
    with pytest.raises(McpToolError):
        await check_shopping_items(str(shopping_list.id), [str(item.id)])
    with pytest.raises(McpToolError):
        await add_shopping_items(str(other.id), ["x"])

    reloaded = h2_user.repos.group_shopping_list_item.get_one(item.id)
    assert reloaded is not None and not reloaded.checked
    assert h2_user.repos.group_shopping_lists.get_one(other.id).list_items[0].note == "secret"
    assert len(h2_user.repos.group_shopping_lists.get_one(other.id).list_items) == 1


@pytest.mark.asyncio
async def test_get_default_list_without_lists_is_not_found(
    monkeypatch: pytest.MonkeyPatch, session: Session, g2_user: TestUser
):
    _as_user(monkeypatch, session, g2_user)
    with pytest.raises(McpToolError):
        await get_shopping_list()
