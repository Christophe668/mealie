import contextlib
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError
from mealie.mcp.server import mcp_server
from mealie.mcp.tools.feedback import get_recipe_feedback, record_recipe_feedback
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

SCOPES = ["recipes:read", "recipes:write"]

ITEM_KEYS = {"id", "recipe", "verdict", "effort", "note", "for_whom", "made_on", "recorded_by"}


def _as_user(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, scopes: list[str] = SCOPES) -> None:
    token = AccessToken(token="t", client_id="c", scopes=scopes, subject=str(user.user_id))
    monkeypatch.setattr(context, "get_access_token", lambda: token)
    monkeypatch.setattr(auth, "get_access_token", lambda: token)
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))


def _create_recipe(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.recipes, json={"name": random_string(12)}, headers=user.token)
    assert response.status_code == 201
    response = api_client.get(api_routes.recipes_slug(response.json()), headers=user.token)
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_record_by_slug_and_id(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user)

    result = await record_recipe_feedback(
        recipe["slug"], "loved", effort=2, note="Crispy", for_whom="Sam", made_on="2026-10-20"
    )

    feedback = result["feedback"]
    assert set(feedback) == ITEM_KEYS
    assert feedback["recipe"] == {"id": recipe["id"], "slug": recipe["slug"], "name": recipe["name"]}
    assert feedback["verdict"] == "loved"
    assert (feedback["effort"], feedback["note"], feedback["for_whom"]) == (2, "Crispy", "Sam")
    assert feedback["made_on"] == "2026-10-20"
    assert feedback["recorded_by"] == user.full_name
    assert result["summary"]["last_verdict"] == "loved"
    assert result["summary"]["last_made_on"] == "2026-10-20"
    assert result["summary"]["total"] == 1

    result = await record_recipe_feedback(recipe["id"], "never_again", made_on="2026-10-22")
    assert result["feedback"]["recipe"]["slug"] == recipe["slug"]
    assert result["summary"]["last_verdict"] == "never_again"
    assert result["summary"]["total"] == 2
    assert result["summary"]["loved"] == 1
    assert result["summary"]["never_again"] == 1


@pytest.mark.asyncio
async def test_record_defaults_made_on_to_today(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user)

    result = await record_recipe_feedback(recipe["slug"], "ok")

    assert result["feedback"]["made_on"] == datetime.now().astimezone().date().isoformat()
    assert result["feedback"]["effort"] is None


@pytest.mark.asyncio
async def test_record_requires_recipes_write(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user, scopes=["recipes:read"])

    with pytest.raises(McpToolError, match="recipes:write"):
        await record_recipe_feedback(recipe["slug"], "loved")
    assert user.repos.recipe_feedback.summaries([UUID(recipe["id"])]) == {}

    # reading only needs recipes:read
    assert (await get_recipe_feedback())["items"] == []


@pytest.mark.asyncio
async def test_get_feedback_requires_recipes_read(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    _as_user(monkeypatch, session, unique_user_fn_scoped, scopes=["mealplan:write"])
    with pytest.raises(McpToolError, match="recipes:read"):
        await get_recipe_feedback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs, field",
    [
        ({"verdict": "great"}, "verdict"),
        ({"verdict": "loved", "effort": 0}, "effort"),
        ({"verdict": "loved", "effort": 4}, "effort"),
        ({"verdict": "loved", "made_on": "20/10/2026"}, "made_on"),
        ({"verdict": "loved", "made_on": "2026-02-30"}, "made_on"),
        ({"verdict": "loved", "made_on": "20261020"}, "made_on"),
        ({"verdict": "loved", "made_on": "2026-W43-1"}, "made_on"),
    ],
)
async def test_record_validates_before_writing(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    api_client: TestClient,
    unique_user_fn_scoped: TestUser,
    kwargs: dict,
    field: str,
):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user)

    with pytest.raises(McpToolError, match=field):
        await record_recipe_feedback(recipe["slug"], **kwargs)

    session.expire_all()
    assert user.repos.recipe_feedback.summaries([UUID(recipe["id"])]) == {}
    events = user.repos.recipe_timeline_events.multi_query({"recipe_id": UUID(recipe["id"])})
    assert [e for e in events if e.event_type == "comment"] == []  # only the "recipe created" event


@pytest.mark.asyncio
async def test_record_rejects_made_on_after_tomorrow(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user)
    today = datetime.now().astimezone().date()

    with pytest.raises(McpToolError, match="made_on"):
        await record_recipe_feedback(recipe["slug"], "loved", made_on=(today + timedelta(days=2)).isoformat())

    session.expire_all()
    assert user.repos.recipe_feedback.summaries([UUID(recipe["id"])]) == {}

    tomorrow = (today + timedelta(days=1)).isoformat()
    result = await record_recipe_feedback(recipe["slug"], "loved", made_on=tomorrow)
    assert result["feedback"]["made_on"] == tomorrow


@pytest.mark.asyncio
async def test_record_blank_note_and_for_whom_become_none(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user)

    result = await record_recipe_feedback(recipe["slug"], "ok", note="   ", for_whom="\t\n")
    assert (result["feedback"]["note"], result["feedback"]["for_whom"]) == (None, None)

    result = await record_recipe_feedback(recipe["slug"], "ok", note="  Too salty ", for_whom=" Sam ")
    assert (result["feedback"]["note"], result["feedback"]["for_whom"]) == ("Too salty", "Sam")


@pytest.mark.asyncio
async def test_record_schema_advertises_verdict_and_effort_values():
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}
    schema = tools["record_recipe_feedback"].input_schema
    props = schema["properties"]
    assert props["verdict"]["enum"] == ["loved", "ok", "never_again"]
    effort_enums = [opt.get("enum") for opt in props["effort"].get("anyOf", [props["effort"]])]
    assert [1, 2, 3] in effort_enums
    assert schema["required"] == ["recipe", "verdict"]


@pytest.mark.asyncio
async def test_record_unknown_recipe_not_found(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    _as_user(monkeypatch, session, unique_user_fn_scoped)
    with pytest.raises(McpToolError, match="recipe not found: no-such-recipe"):
        await record_recipe_feedback("no-such-recipe", "loved")
    with pytest.raises(McpToolError, match="recipe not found"):
        await get_recipe_feedback("no-such-recipe")


@pytest.mark.asyncio
async def test_get_one_recipe_and_latest_across_recipes(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe_a = _create_recipe(api_client, user)
    recipe_b = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user)

    a_old = (await record_recipe_feedback(recipe_a["slug"], "ok", made_on="2026-10-01"))["feedback"]
    b_new = (await record_recipe_feedback(recipe_b["slug"], "loved", made_on="2026-10-15"))["feedback"]
    a_new = (await record_recipe_feedback(recipe_a["slug"], "loved", made_on="2026-10-10"))["feedback"]

    one = await get_recipe_feedback(recipe_a["slug"])
    assert [i["id"] for i in one["items"]] == [a_new["id"], a_old["id"]]
    assert set(one["items"][0]) == ITEM_KEYS
    assert one["total"] == 2

    by_id = await get_recipe_feedback(recipe_a["id"])
    assert [i["id"] for i in by_id["items"]] == [a_new["id"], a_old["id"]]

    latest = await get_recipe_feedback()
    assert [i["id"] for i in latest["items"]] == [b_new["id"], a_new["id"], a_old["id"]]
    assert latest["items"][0]["recipe"]["name"] == recipe_b["name"]

    assert [i["id"] for i in (await get_recipe_feedback(limit=1))["items"]] == [b_new["id"]]
    assert len((await get_recipe_feedback(limit=0))["items"]) == 1  # clamped up to 1
    assert len((await get_recipe_feedback(limit=500))["items"]) == 3  # clamped down to 50


@pytest.mark.asyncio
async def test_feedback_isolated_between_households(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    api_client: TestClient,
    unique_user: TestUser,
    h2_user: TestUser,
    g2_user: TestUser,
):
    shared = _create_recipe(api_client, unique_user)

    # another household of the group can record on the shared recipe; it lands in its own household
    _as_user(monkeypatch, session, h2_user)
    theirs = (await record_recipe_feedback(shared["slug"], "never_again"))["feedback"]
    assert [i["id"] for i in (await get_recipe_feedback(shared["slug"]))["items"]] == [theirs["id"]]

    _as_user(monkeypatch, session, unique_user)
    assert (await get_recipe_feedback(shared["slug"]))["items"] == []
    assert theirs["id"] not in [i["id"] for i in (await get_recipe_feedback(limit=50))["items"]]
    mine = await record_recipe_feedback(shared["slug"], "loved")
    assert mine["summary"]["total"] == 1
    assert mine["summary"]["last_verdict"] == "loved"

    # another group cannot see the recipe at all
    _as_user(monkeypatch, session, g2_user)
    with pytest.raises(McpToolError, match="recipe not found"):
        await record_recipe_feedback(shared["slug"], "loved")
    with pytest.raises(McpToolError, match="recipe not found"):
        await get_recipe_feedback(shared["id"])
