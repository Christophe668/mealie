import contextlib
from datetime import date, timedelta
from uuid import uuid4

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mealie.core.exceptions import NoEntryFound
from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError
from mealie.mcp.scopes import ALL_SCOPES
from mealie.mcp.tools import pantry as pantry_tools
from mealie.mcp.tools.pantry import get_pantry, put_away_shopping_items, update_pantry
from mealie.schema.household.group_shopping_list import ShoppingListItemCreate, ShoppingListSave
from mealie.schema.household.pantry import PantryItemCreate, PantryLocation
from mealie.schema.recipe.recipe_ingredient import SaveIngredientFood, SaveIngredientUnit
from mealie.services.claude_context.pantry_service import PantryService
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

SCOPES = ["recipes:read", "pantry:write"]
TODAY = date(2026, 10, 24)


def _as_user(
    monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, scopes: list[str] | None = None
) -> None:
    token = AccessToken(token="t", client_id="c", scopes=scopes or SCOPES, subject=str(user.user_id))
    monkeypatch.setattr(context, "get_access_token", lambda: token)
    monkeypatch.setattr(auth, "get_access_token", lambda: token)
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))
    monkeypatch.setattr(pantry_tools, "_today", lambda: TODAY)


def _add(user: TestUser, **fields) -> str:
    item, _ = PantryService(user.repos).add_item(PantryItemCreate(**fields))
    return str(item.id)


def test_scopes_include_pantry_write():
    assert "pantry:write" in ALL_SCOPES


@pytest.mark.asyncio
async def test_get_pantry_orders_and_counts_days(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _add(user, name="Rice", location=PantryLocation.cupboard, bought_on=TODAY - timedelta(days=30))
    _add(
        user,
        name="Milk",
        location=PantryLocation.fridge,
        bought_on=TODAY - timedelta(days=3),
        opened_on=TODAY - timedelta(days=2),
        use_by=TODAY + timedelta(days=1),
    )
    _add(user, name="Yoghurt", location=PantryLocation.fridge, use_by=TODAY + timedelta(days=9))
    _as_user(monkeypatch, session, user)

    result = await get_pantry()

    assert [i["name"] for i in result["items"]] == ["Milk", "Yoghurt", "Rice"]
    milk = result["items"][0]
    assert set(milk) == {
        "id",
        "name",
        "food_id",
        "quantity",
        "unit",
        "location",
        "bought_on",
        "opened_on",
        "use_by",
        "source",
        "note",
        "days_since_bought",
        "days_since_opened",
        "days_until_use_by",
        "shelf_life_days_opened",
        "shelf_life_days_unopened",
    }
    assert milk["location"] == "fridge"
    assert milk["use_by"] == (TODAY + timedelta(days=1)).isoformat()
    assert milk["days_since_bought"] == 3
    assert milk["days_since_opened"] == 2
    assert milk["days_until_use_by"] == 1
    rice = result["items"][2]
    assert rice["days_since_bought"] == 30
    assert rice["days_since_opened"] is None
    assert rice["days_until_use_by"] is None
    assert rice["shelf_life_days_opened"] is None

    fridge = await get_pantry("fridge")
    assert [i["name"] for i in fridge["items"]] == ["Milk", "Yoghurt"]

    with pytest.raises(McpToolError, match="fridge, freezer, cupboard, other"):
        await get_pantry("garage")


@pytest.mark.asyncio
async def test_get_pantry_reads_shelf_life_from_food_extras(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    food = user.repos.ingredient_foods.create(
        SaveIngredientFood(
            name=random_string(10),
            group_id=user.group_id,
            extras={"shelf_life_days_opened": "4", "shelf_life_days_unopened": "not a number"},
        )
    )
    _add(user, name=food.name, food_id=food.id)
    _as_user(monkeypatch, session, user)

    (item,) = (await get_pantry())["items"]

    assert item["food_id"] == str(food.id)
    assert item["shelf_life_days_opened"] == 4
    assert item["shelf_life_days_unopened"] is None


@pytest.mark.asyncio
async def test_update_pantry_add_update_remove_in_one_call(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    eggs = _add(user, name="Eggs", quantity=6, location=PantryLocation.fridge)
    jam = _add(user, name="Jam", location=PantryLocation.cupboard)
    old = _add(user, name="Old bread")
    _as_user(monkeypatch, session, user)

    result = await update_pantry(
        add=[
            {"name": "eggs", "quantity": 6, "location": "fridge"},
            {"name": "Butter", "location": "fridge", "bought_on": "2026-10-20"},
        ],
        update=[{"id": jam, "opened_on": "2026-10-23", "location": "fridge"}],
        remove=[old],
    )

    by_name = {i["name"]: i for i in result["items"]}
    assert set(by_name) == {"Eggs", "Jam", "Butter"}
    assert result["merged_ids"] == [eggs]
    assert by_name["Eggs"]["quantity"] == 12
    assert result["added_ids"] == [by_name["Butter"]["id"]]
    assert by_name["Butter"]["days_since_bought"] == 4
    assert result["updated_ids"] == [jam]
    assert by_name["Jam"]["opened_on"] == "2026-10-23"
    assert by_name["Jam"]["location"] == "fridge"
    assert by_name["Jam"]["days_since_opened"] == 1
    assert result["removed_ids"] == [old]


@pytest.mark.asyncio
async def test_update_pantry_rejects_unknown_keys_before_writing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    keep = _add(user, name="Keep me")
    _as_user(monkeypatch, session, user)

    with pytest.raises(McpToolError, match="expiry"):
        await update_pantry(add=[{"name": "Cheese"}, {"name": "Ham", "expiry": "2026-11-01"}], remove=[keep])
    with pytest.raises(McpToolError, match="use_by"):
        await update_pantry(update=[{"id": keep, "use_by": "next week"}], add=[{"name": "Cheese"}])
    with pytest.raises(McpToolError, match="pantry_item not found"):
        await update_pantry(add=[{"name": "Cheese"}], remove=[str(uuid4())])
    with pytest.raises(McpToolError, match="food_id"):
        await update_pantry(add=[{"name": "Cheese", "food_id": "not-a-uuid"}], remove=[keep])
    with pytest.raises(McpToolError, match="food not found"):
        await update_pantry(add=[{"name": "Cheese", "food_id": str(uuid4())}], remove=[keep])
    with pytest.raises(McpToolError, match="unit not found: furlong"):
        await update_pantry(add=[{"name": "Cheese", "unit": "furlong"}], remove=[keep])

    assert [i["name"] for i in (await get_pantry())["items"]] == ["Keep me"]


@pytest.mark.asyncio
async def test_update_pantry_requires_scope(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user, scopes=["recipes:read", "shopping:write"])

    with pytest.raises(McpToolError, match="missing required scope: pantry:write"):
        await update_pantry(add=[{"name": "Cheese"}])
    with pytest.raises(McpToolError, match="missing required scope: pantry:write"):
        await put_away_shopping_items(str(uuid4()))
    assert user.repos.pantry_items.ordered(None) == []


@pytest.mark.asyncio
async def test_update_pantry_isolated_by_household(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, h2_user: TestUser
):
    theirs = _add(h2_user, name=random_string(10))
    _as_user(monkeypatch, session, unique_user)

    assert theirs not in {i["id"] for i in (await get_pantry())["items"]}
    with pytest.raises(McpToolError, match=f"pantry_item not found: {theirs}"):
        await update_pantry(update=[{"id": theirs, "note": "mine now"}])
    with pytest.raises(McpToolError, match=f"pantry_item not found: {theirs}"):
        await update_pantry(remove=[theirs])

    item = h2_user.repos.pantry_items.get_one(theirs)
    assert item is not None
    assert item.note is None


def _list_with_items(user: TestUser, checked: dict[str, bool]) -> tuple[str, dict[str, str]]:
    shopping_list = user.repos.group_shopping_lists.create(
        ShoppingListSave(name=random_string(8), group_id=user.group_id, user_id=user.user_id)
    )
    ids = {}
    for note, is_checked in checked.items():
        item = user.repos.group_shopping_list_item.create(
            ShoppingListItemCreate(shopping_list_id=shopping_list.id, note=note, is_food=False, checked=is_checked)
        )
        ids[note] = str(item.id)
    return str(shopping_list.id), ids


@pytest.mark.asyncio
async def test_put_away_tool_matches_rest(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _add(user, name="Pasta", quantity=1)
    list_id, ids = _list_with_items(user, {"Pasta": True, "Apples": True, "Bread": False})
    _as_user(monkeypatch, session, user)

    result = await put_away_shopping_items(list_id)

    assert set(result) == {"created", "merged", "removed_item_ids"}
    assert [i["name"] for i in result["created"]] == ["Apples"]
    assert result["created"][0]["source"] == "shopping"
    assert result["created"][0]["bought_on"] == TODAY.isoformat()
    assert result["created"][0]["days_since_bought"] == 0
    assert [i["name"] for i in result["merged"]] == ["Pasta"]
    assert sorted(result["removed_item_ids"]) == sorted([ids["Pasta"], ids["Apples"]])

    # same outcome through REST on a twin list: same buckets, same removed ids
    rest_list_id, rest_ids = _list_with_items(user, {"Pasta": True, "Apples": True, "Bread": False})
    response = api_client.post(
        api_routes.households_shopping_lists_list_id_put_away(rest_list_id), json={}, headers=user.token
    )
    assert response.status_code == 200
    rest = response.json()
    assert sorted(rest["removedItemIds"]) == sorted([rest_ids["Pasta"], rest_ids["Apples"]])
    assert sorted(i["name"] for i in rest["merged"]) == ["Apples", "Pasta"]

    with pytest.raises(McpToolError, match="shopping_list not found"):
        await put_away_shopping_items(str(uuid4()))


@pytest.mark.asyncio
async def test_put_away_tool_unchecked_ids_error(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    list_id, ids = _list_with_items(user, {"Eggs": True, "Bread": False})
    _as_user(monkeypatch, session, user)

    with pytest.raises(McpToolError, match=f"not checked.*{ids['Bread']}"):
        await put_away_shopping_items(list_id, [ids["Eggs"], ids["Bread"]])

    assert (await get_pantry())["items"] == []
    assert len(user.repos.group_shopping_lists.get_one(list_id).list_items) == 2


@pytest.mark.asyncio
async def test_put_away_tool_refuses_another_households_list(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, h2_user: TestUser
):
    list_id, ids = _list_with_items(h2_user, {random_string(8): True})
    (item_id,) = ids.values()
    before = {u.user_id: len(u.repos.pantry_items.get_all()) for u in (unique_user, h2_user)}
    _as_user(monkeypatch, session, unique_user)

    with pytest.raises(McpToolError, match=f"shopping_list not found: {list_id}"):
        await put_away_shopping_items(list_id)
    with pytest.raises(McpToolError, match=f"shopping_list not found: {list_id}"):
        await put_away_shopping_items(list_id, [item_id])

    assert h2_user.repos.group_shopping_list_item.get_one(item_id) is not None
    assert {u.user_id: len(u.repos.pantry_items.get_all()) for u in (unique_user, h2_user)} == before


@pytest.mark.asyncio
async def test_update_pantry_rejects_blank_names_before_writing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    keep = _add(user, name="Keep me")
    _as_user(monkeypatch, session, user)

    with pytest.raises(McpToolError, match=r"add\[1\].*name"):
        await update_pantry(add=[{"name": "Cheese"}, {"name": "   "}], remove=[keep])
    with pytest.raises(McpToolError, match=r"update\[0\].*name"):
        await update_pantry(update=[{"id": keep, "name": ""}], add=[{"name": "Cheese"}])

    assert [i["name"] for i in (await get_pantry())["items"]] == ["Keep me"]


@pytest.mark.asyncio
async def test_update_pantry_rejects_repeated_and_conflicting_ids(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    a = _add(user, name="Apples")
    b = _add(user, name="Bananas")
    _as_user(monkeypatch, session, user)

    with pytest.raises(McpToolError, match=f"update: repeated id {a}"):
        await update_pantry(update=[{"id": a, "note": "first"}, {"id": a, "location": "fridge"}])
    with pytest.raises(McpToolError, match=f"remove: repeated id.*{b}"):
        await update_pantry(remove=[b, b])
    with pytest.raises(McpToolError, match=f"{a} is also in remove"):
        await update_pantry(update=[{"id": a, "note": "x"}], remove=[a])

    items = (await get_pantry())["items"]
    assert sorted(i["name"] for i in items) == ["Apples", "Bananas"]
    assert all(i["note"] is None and i["location"] == "cupboard" for i in items)


@pytest.mark.asyncio
async def test_update_pantry_keeps_omitted_fields_and_null_clears(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    milk = _add(
        user,
        name="Milk",
        quantity=2,
        location=PantryLocation.fridge,
        bought_on=TODAY - timedelta(days=1),
        use_by=TODAY + timedelta(days=5),
        note="semi-skimmed",
    )
    _as_user(monkeypatch, session, user)

    result = await update_pantry(update=[{"id": milk, "opened_on": TODAY.isoformat(), "note": None}])

    (item,) = result["items"]
    assert item["opened_on"] == TODAY.isoformat()
    assert item["note"] is None
    assert item["name"] == "Milk"
    assert item["quantity"] == 2
    assert item["location"] == "fridge"
    assert item["bought_on"] == (TODAY - timedelta(days=1)).isoformat()
    assert item["use_by"] == (TODAY + timedelta(days=5)).isoformat()


@pytest.mark.asyncio
async def test_update_pantry_unit_by_name(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    unit = user.repos.ingredient_units.create(
        SaveIngredientUnit(name=random_string(8), abbreviation=random_string(3), group_id=user.group_id)
    )
    _as_user(monkeypatch, session, user)

    with pytest.raises(McpToolError, match="either unit or unit_id"):
        await update_pantry(add=[{"name": "Flour", "unit": unit.name, "unit_id": str(unit.id)}])

    result = await update_pantry(add=[{"name": "Flour", "quantity": 500, "unit": unit.abbreviation.upper()}])

    assert result["items"][0]["unit"] == unit.name


@pytest.mark.asyncio
async def test_update_pantry_race_reports_the_item_id(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    item_id = _add(user, name="Gone soon")
    _as_user(monkeypatch, session, user)

    def vanished(self, *args, **kwargs):
        raise NoEntryFound("Food not found.")

    # the row passes validation, then disappears before the write
    monkeypatch.setattr(PantryService, "update_item", vanished)

    with pytest.raises(McpToolError, match=f"^pantry_item not found: {item_id}$"):
        await update_pantry(update=[{"id": item_id, "note": "x"}])
