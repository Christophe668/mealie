import contextlib
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError
from mealie.mcp.tools import recipes as recipes_module
from mealie.mcp.tools.household import get_household_context
from mealie.mcp.tools.recipes import _build_pagination, _resolve_organizers, get_recipe, search_recipes
from mealie.repos.all_repositories import get_repositories
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackCreate
from mealie.schema.response.pagination import OrderByNullPosition, OrderDirection
from mealie.schema.user.user import PrivateUser
from mealie.services.claude_context.recipe_feedback_service import RecipeFeedbackService
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

SCOPES = ["recipes:read"]


def _as_user(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, scopes: list[str] = SCOPES) -> None:
    token = AccessToken(token="t", client_id="c", scopes=scopes, subject=str(user.user_id))
    monkeypatch.setattr(context, "get_access_token", lambda: token)
    monkeypatch.setattr(auth, "get_access_token", lambda: token)
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))


def _create_recipe(api_client: TestClient, user: TestUser, name: str | None = None, **updates) -> str:
    response = api_client.post(api_routes.recipes, json={"name": name or random_string(12)}, headers=user.token)
    assert response.status_code == 201
    slug = response.json()
    if updates:
        body = api_client.get(api_routes.recipes_slug(slug), headers=user.token).json()
        body.update(updates)
        response = api_client.put(api_routes.recipes_slug(slug), json=body, headers=user.token)
        assert response.status_code == 200, response.text
    return slug


def _create_tag(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.organizers_tags, json={"name": random_string(10)}, headers=user.token)
    assert response.status_code == 201
    tag = response.json()
    return {"id": tag["id"], "groupId": str(user.group_id), "name": tag["name"], "slug": tag["slug"]}


@pytest.mark.asyncio
async def test_get_household_context_shape(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser):
    _as_user(monkeypatch, session, unique_user)

    result = await get_household_context()

    assert result["group"]["id"] == str(unique_user.group_id)
    assert result["group"]["name"]
    assert result["group"]["slug"]
    assert result["household"]["id"] == str(unique_user.household_id)
    assert result["household"]["name"]
    member_ids = [m["id"] for m in result["members"]]
    assert str(unique_user.user_id) in member_ids
    assert {"id", "full_name", "username"} <= set(result["members"][0])
    assert result["user"] == {"id": str(unique_user.user_id), "full_name": unique_user.full_name}
    assert isinstance(result["first_day_of_week"], int)
    assert result["locale"]
    assert result["today"] == datetime.now().astimezone().date().isoformat()
    assert result["scopes_granted"] == SCOPES
    assert result["preferences"] == {"members": [], "household": None}


@pytest.mark.asyncio
async def test_household_context_requires_scope(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser
):
    _as_user(monkeypatch, session, unique_user, scopes=["mealplan:write"])

    with pytest.raises(McpToolError, match="recipes:read"):
        await get_household_context()


@pytest.mark.asyncio
async def test_search_by_tag_and_max_time(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    tag = _create_tag(api_client, unique_user)
    quick = _create_recipe(api_client, unique_user, tags=[tag], totalTimeSeconds=20 * 60, totalTime="20 minutes")
    _create_recipe(api_client, unique_user, tags=[tag], totalTimeSeconds=90 * 60)
    _create_recipe(api_client, unique_user, totalTimeSeconds=10 * 60)  # untagged
    _as_user(monkeypatch, session, unique_user)

    result = await search_recipes(tags=[tag["name"]], max_total_minutes=30)

    assert result["total"] == 1
    assert [r["slug"] for r in result["items"]] == [quick]
    brief = result["items"][0]
    assert brief["tags"] == [tag["name"]]
    assert brief["total_time"] == "20 minutes"
    assert brief["last_made"] is None
    assert brief["url"].endswith(f"/r/{quick}")
    assert set(brief) == {
        "id",
        "slug",
        "name",
        "description",
        "total_time",
        "prep_time",
        "servings",
        "rating",
        "tags",
        "categories",
        "last_made",
        "last_verdict",
        "url",
    }

    unknown = await search_recipes(tags=["no-such-tag-" + random_string(6)])
    assert unknown["total"] == 0
    assert unknown["items"] == []


@pytest.mark.asyncio
async def test_search_not_made_since_days(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    tag = _create_tag(api_client, unique_user)
    recent = _create_recipe(api_client, unique_user, tags=[tag])
    never = _create_recipe(api_client, unique_user, tags=[tag])
    now = datetime.now(UTC)
    stamp = {"timestamp": now.isoformat().replace("+00:00", "Z")}
    response = api_client.patch(api_routes.recipes_slug_last_made(recent), json=stamp, headers=unique_user.token)
    assert response.status_code == 200
    _as_user(monkeypatch, session, unique_user)

    everything = await search_recipes(tags=[tag["slug"]], order_by="last_made")
    by_slug = {r["slug"]: r for r in everything["items"]}
    assert by_slug[recent]["last_made"] == now.date().isoformat()  # stored as UTC
    assert by_slug[never]["last_made"] is None

    result = await search_recipes(tags=[tag["slug"]], not_made_since_days=7)
    assert [r["slug"] for r in result["items"]] == [never]


@pytest.mark.parametrize("order_by", ["name", "rating", "random", "last_made", "created_at"])
def test_pagination_orders_nulls_last(order_by):
    pagination = _build_pagination(order_by, 1, 20, None, lambda: "seed")

    # NULL ratings would sort first on Postgres with DESC; SQLite hides it, so check the query itself
    assert pagination.order_by_null_position is OrderByNullPosition.last
    assert pagination.pagination_seed == ("seed" if order_by == "random" else None)
    if order_by == "rating":
        assert pagination.order_direction is OrderDirection.desc


@pytest.mark.asyncio
async def test_search_by_rating_puts_unrated_last(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    tag = _create_tag(api_client, unique_user)
    unrated = _create_recipe(api_client, unique_user, tags=[tag])
    rated = _create_recipe(api_client, unique_user, tags=[tag])
    response = api_client.post(
        api_routes.users_id_ratings_slug(unique_user.user_id, rated), json={"rating": 4}, headers=unique_user.token
    )
    assert response.status_code == 200
    _as_user(monkeypatch, session, unique_user)

    captured = []
    original = recipes_module._build_pagination
    monkeypatch.setattr(recipes_module, "_build_pagination", lambda *a: captured.append(original(*a)) or captured[-1])

    result = await search_recipes(tags=[tag["slug"]], order_by="rating")

    assert [r["slug"] for r in result["items"]] == [rated, unrated]
    assert captured[0].order_by_null_position is OrderByNullPosition.last


def test_resolve_organizers_ambiguous_name_raises():
    class AmbiguousRepo:
        def get_one(self, value, key, any_case=False):
            if key == "slug":
                return None
            raise MultipleResultsFound()

    with pytest.raises(McpToolError, match="ambiguous.*Dinner"):
        _resolve_organizers(AmbiguousRepo(), ["Dinner"])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_search_random_is_seeded_per_call(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    tag = _create_tag(api_client, unique_user)
    for _ in range(3):
        _create_recipe(api_client, unique_user, tags=[tag])
    _as_user(monkeypatch, session, unique_user)

    first = await search_recipes(tags=[tag["name"]], order_by="random")
    second = await search_recipes(tags=[tag["name"]], order_by="random")

    assert first["total"] == second["total"] == 3
    assert {r["slug"] for r in first["items"]} == {r["slug"] for r in second["items"]}


@pytest.mark.asyncio
async def test_get_recipe_by_slug_and_unknown_raises_not_found(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    tag = _create_tag(api_client, unique_user)
    slug = _create_recipe(
        api_client,
        unique_user,
        description="A test dish",
        tags=[tag],
        recipeIngredient=[{"note": "2 eggs", "display": "2 eggs"}],
        recipeInstructions=[{"title": "", "text": "Whisk the eggs."}],
        notes=[{"title": "Tip", "text": "Use fresh eggs."}],
    )
    _as_user(monkeypatch, session, unique_user)

    recipe = await get_recipe(slug)

    assert recipe["slug"] == slug
    assert recipe["description"] == "A test dish"
    assert recipe["tags"] == [tag["name"]]
    assert recipe["ingredients"][0]["display"] == "2 eggs"
    assert set(recipe["ingredients"][0]) == {"quantity", "unit", "food", "note", "display", "ref", "section"}
    assert recipe["ingredients"][0]["section"] is None
    assert UUID(recipe["ingredients"][0]["ref"])
    assert recipe["instructions"] == [{"title": "", "text": "Whisk the eggs.", "timer_minutes": None, "uses": []}]
    assert recipe["notes"] == [{"title": "Tip", "text": "Use fresh eggs."}]
    assert recipe["url"].endswith(f"/r/{slug}")
    assert set(recipe["times"]) == {"total", "prep", "cook"}

    by_id = await get_recipe(recipe["id"])
    assert by_id["slug"] == slug

    with pytest.raises(McpToolError, match="not found"):
        await get_recipe("no-such-recipe-" + random_string(6))


@pytest.mark.asyncio
async def test_search_only_sees_own_group(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    api_client: TestClient,
    unique_user: TestUser,
    g2_user: TestUser,
):
    name = "Isolation " + random_string(10)
    other_slug = _create_recipe(api_client, g2_user, name=name)
    _as_user(monkeypatch, session, unique_user)

    result = await search_recipes(query=name)

    assert other_slug not in [r["slug"] for r in result["items"]]
    with pytest.raises(McpToolError, match="not found"):
        await get_recipe(other_slug)


@pytest.mark.asyncio
async def test_search_sees_other_household_same_group(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    api_client: TestClient,
    unique_user: TestUser,
    h2_user: TestUser,
):
    name = "Shared " + random_string(10)
    other_slug = _create_recipe(api_client, h2_user, name=name)
    _as_user(monkeypatch, session, unique_user)

    result = await search_recipes(query=name)

    assert other_slug in [r["slug"] for r in result["items"]]
    assert (await get_recipe(other_slug))["slug"] == other_slug


def _record_feedback(user: TestUser, slug: str, verdict: FeedbackVerdict, made_on: date) -> None:
    # group-wide lookup: the recipe may belong to another household of the group
    recipe = get_repositories(user.repos.session, group_id=user.group_id, household_id=None).recipes.get_one(
        slug, "slug"
    )
    assert recipe is not None
    private_user = user.repos.users.get_one(user.user_id)
    assert isinstance(private_user, PrivateUser)
    RecipeFeedbackService(user.repos, private_user).record(
        RecipeFeedbackCreate(recipe_id=recipe.id, verdict=verdict, made_on=made_on)
    )


@pytest.mark.asyncio
async def test_search_items_carry_last_verdict(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user: TestUser
):
    prefix = "Verdict " + random_string(8)
    rated = _create_recipe(api_client, unique_user, name=f"{prefix} A")
    plain = _create_recipe(api_client, unique_user, name=f"{prefix} B")
    _record_feedback(unique_user, rated, FeedbackVerdict.loved, date(2026, 10, 1))
    _record_feedback(unique_user, rated, FeedbackVerdict.never_again, date(2026, 10, 5))
    _as_user(monkeypatch, session, unique_user)

    calls: list[int] = []
    original = RecipeFeedbackService.summaries

    def counting(self, ids):
        calls.append(len(ids))
        return original(self, ids)

    monkeypatch.setattr(RecipeFeedbackService, "summaries", counting)

    result = await search_recipes(query=prefix)

    verdicts = {r["slug"]: r["last_verdict"] for r in result["items"]}
    assert {rated: verdicts.get(rated), plain: verdicts.get(plain, "missing")} == {rated: "never_again", plain: None}
    assert calls == [len(result["items"])]  # one batched lookup per search, for every item


def _verdict_of(result: dict, slug: str) -> str | None:
    (item,) = [r for r in result["items"] if r["slug"] == slug]  # the free-text search may match others too
    return item["last_verdict"]


@pytest.mark.asyncio
async def test_last_verdict_is_per_household(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    api_client: TestClient,
    unique_user: TestUser,
    h2_user: TestUser,
):
    name = "Household verdict " + random_string(8)
    slug = _create_recipe(api_client, unique_user, name=name)
    _record_feedback(h2_user, slug, FeedbackVerdict.never_again, date(2026, 10, 5))

    _as_user(monkeypatch, session, unique_user)
    assert _verdict_of(await search_recipes(query=name), slug) is None
    recipe = await get_recipe(slug)
    assert recipe["feedback"] == []
    assert recipe["feedback_summary"] is None

    _as_user(monkeypatch, session, h2_user)
    assert _verdict_of(await search_recipes(query=name), slug) == "never_again"


@pytest.mark.asyncio
async def test_get_recipe_includes_latest_feedback_and_summary(
    monkeypatch: pytest.MonkeyPatch, session: Session, api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    slug = _create_recipe(api_client, user)
    _as_user(monkeypatch, session, user)

    recipe = await get_recipe(slug)
    assert recipe["feedback"] == []
    assert recipe["feedback_summary"] is None

    for day in range(1, 8):
        verdict = FeedbackVerdict.loved if day % 2 else FeedbackVerdict.ok
        _record_feedback(user, slug, verdict, date(2026, 10, day))

    recipe = await get_recipe(slug)

    assert [f["made_on"] for f in recipe["feedback"]] == [f"2026-10-0{d}" for d in (7, 6, 5, 4, 3)]
    assert set(recipe["feedback"][0]) == {
        "id",
        "recipe",
        "verdict",
        "effort",
        "note",
        "for_whom",
        "made_on",
        "recorded_by",
    }
    assert recipe["feedback"][0]["verdict"] == "loved"
    assert recipe["feedback"][0]["recorded_by"] == user.full_name
    summary = recipe["feedback_summary"]
    assert summary["last_verdict"] == "loved"
    assert summary["last_made_on"] == "2026-10-07"
    assert (summary["loved"], summary["ok"], summary["never_again"], summary["total"]) == (4, 3, 0, 7)
