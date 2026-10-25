import contextlib
import inspect
from collections.abc import Callable
from typing import Any

import pytest
from mcp.server.auth.provider import AccessToken
from pydantic import ValidationError
from sqlalchemy.orm import Session

from mealie.mcp import auth, context
from mealie.mcp import tools as tools_package
from mealie.mcp.errors import McpToolError
from mealie.mcp.server import INSTRUCTIONS, mcp_server
from mealie.mcp.tools import recipe_write
from mealie.mcp.tools._summaries import time_text
from mealie.mcp.tools.recipe_write import create_recipe, to_tool_error
from mealie.mcp.tools.recipes import get_recipe_impl
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import SaveIngredientFood, SaveIngredientUnit
from mealie.schema.response.pagination import PaginationQuery
from mealie.services.claude_context import recipe_writer as recipe_writer_module
from mealie.services.claude_context.recipe_writer import RecipeCreateIn
from mealie.services.event_bus_service.event_types import EventTypes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

SCOPES = ["recipes:read", "recipes:write"]
POLICY = "Follow the user's own instructions about confirming changes. When they haven't said, confirm before writing."


def _as_user(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, scopes: list[str] = SCOPES) -> None:
    token = AccessToken(token="t", client_id="c", scopes=scopes, subject=str(user.user_id))
    monkeypatch.setattr(context, "get_access_token", lambda: token)
    monkeypatch.setattr(auth, "get_access_token", lambda: token)
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))


@pytest.fixture(autouse=True)
def dispatch_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Event listeners run synchronously in these tests (in production they run on a daemon thread)."""
    monkeypatch.setattr(recipe_writer_module, "dispatch_off_request", lambda task: task())


def _count(repo) -> int:
    return len(repo.page_all(PaginationQuery(page=1, per_page=-1)).items)


def _counts(user: TestUser) -> dict[str, int]:
    repos = user.repos
    return {
        "foods": _count(repos.ingredient_foods),
        "units": _count(repos.ingredient_units),
        "tags": _count(repos.tags),
        "categories": _count(repos.categories),
        "tools": _count(repos.tools),
        "recipes": _count(repos.recipes),
    }


def _stored(user: TestUser, slug: str) -> Recipe:
    user.repos.session.expire_all()
    recipe = user.repos.recipes.get_one(slug)
    assert recipe is not None
    return recipe


# ---------------------------------------------------------------------- create


@pytest.mark.asyncio
async def test_create_minimal(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    name = f"Omelette {random_string(6)}"

    result = await create_recipe(name=name, ingredients=["2 eggs"], instructions=["Whisk and cook."])

    assert result["name"] == name
    assert result["similar_existing"] == []
    assert result["url"].endswith(f"/r/{result['slug']}")
    stored = _stored(user, result["slug"])
    assert str(stored.user_id) == str(user.user_id)
    assert str(stored.household_id) == str(user.household_id)
    assert [s.text for s in stored.recipe_instructions or []] == ["Whisk and cook."]
    assert len(stored.recipe_ingredient) == 1

    with context.mcp_context() as ctx:
        assert get_recipe_impl(ctx, result["slug"])["id"] == result["id"]
        assert get_recipe_impl(ctx, result["id"])["slug"] == result["slug"]


@pytest.mark.asyncio
async def test_create_full(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    food = user.repos.ingredient_foods.create(
        SaveIngredientFood(name=f"guanciale{random_string(4)}", group_id=user.group_id)
    )
    unit = user.repos.ingredient_units.create(
        SaveIngredientUnit(name=random_string(8), abbreviation=random_string(3), group_id=user.group_id)
    )
    new_food = random_string(10)
    tag, category, tool = random_string(8), random_string(8), random_string(8)

    result = await create_recipe(
        name="Carbonara",
        description="Roman classic, no cream.",
        servings=4,
        yield_text="4 plates",
        prep_minutes=10,
        cook_minutes=15,
        total_minutes=25,
        ingredients=[
            {"quantity": 150, "unit": unit.abbreviation, "food": food.name.upper(), "section": "Sauce"},
            {"quantity": 3, "food": new_food, "note": "yolks only"},
            "salt to taste",
        ],
        instructions=[
            {"text": "Crisp the guanciale.", "title": "Sauce", "timer_minutes": 8},
            "Toss with the pasta off the heat.",
        ],
        tags=[tag],
        categories=[category],
        tools=[tool],
        notes=[{"title": "Tip", "text": "Keep some pasta water."}],
        source_url="https://example.com/carbonara",
    )

    stored = _stored(user, result["slug"])
    first, second, third = stored.recipe_ingredient
    assert first.food is not None and first.food.id == food.id
    assert first.unit is not None and first.unit.id == unit.id
    assert first.title == "Sauce" and first.quantity == 150
    assert second.food is not None and second.food.name == new_food and second.note == "yolks only"
    assert third.original_text == "salt to taste"
    steps = stored.recipe_instructions or []
    assert (steps[0].title, steps[0].duration_seconds) == ("Sauce", 480)
    assert steps[1].text == "Toss with the pasta off the heat."
    assert [t.name for t in stored.tags or []] == [tag]
    assert [c.name for c in stored.recipe_category or []] == [category]
    assert [t.name for t in stored.tools] == [tool]
    assert [(n.title, n.text) for n in stored.notes or []] == [("Tip", "Keep some pasta water.")]
    assert stored.org_url == "https://example.com/carbonara"
    assert (stored.prep_time_seconds, stored.perform_time_seconds, stored.total_time_seconds) == (600, 900, 1500)
    assert stored.recipe_servings == 4 and stored.recipe_yield == "4 plates"

    # the response is get_recipe's shape; the times fall back to the structured *_time_seconds
    assert result["times"] == {"total": "25 minutes", "prep": "10 minutes", "cook": "15 minutes"}
    assert result["servings"] == 4
    assert result["org_url"] == "https://example.com/carbonara"
    assert result["tags"] == [tag]
    assert result["ingredients"][0]["food"] == food.name


@pytest.mark.asyncio
async def test_refused_create_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    before = _counts(user)

    with pytest.raises(McpToolError, match=r"instructions\.0"):
        await create_recipe(
            name="Soup",
            ingredients=[{"quantity": 1, "unit": random_string(8), "food": random_string(10)}],
            instructions=[{"text": "  "}],
            tags=[random_string(8)],
        )
    with pytest.raises(McpToolError, match="tags"):
        await create_recipe(
            name="Soup", ingredients=[f"1 {random_string(8)}"], instructions=["Cook."], tags=[random_string(8), "!!!"]
        )
    with pytest.raises(McpToolError, match="name"):
        await create_recipe(name="🍲", ingredients=[f"1 {random_string(8)}"], instructions=["Cook."])

    assert _counts(user) == before


@pytest.mark.asyncio
async def test_create_duplicate_name_lists_earlier_recipes(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    name = f"Dal {random_string(6)}"

    first = await create_recipe(name=name, ingredients=["1 cup lentils"], instructions=["Simmer."])
    second = await create_recipe(name=name.lower(), ingredients=["1 cup lentils"], instructions=["Simmer."])

    assert second["name"] == f"{name.lower()} (1)"
    assert second["slug"] != first["slug"]
    assert [s["slug"] for s in second["similar_existing"]] == [first["slug"]]
    assert set(second["similar_existing"][0]) == {"name", "slug", "url"}


@pytest.mark.asyncio
async def test_create_publishes_event(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    calls: list[dict[str, Any]] = []

    class FakeBus:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dispatch(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(recipe_writer_module, "EventBusService", FakeBus)

    result = await create_recipe(name="Toast", ingredients=["1 slice bread"], instructions=["Toast it."])

    assert [c["event_type"] for c in calls] == [EventTypes.recipe_created]
    assert calls[0]["document_data"].recipe_slug == result["slug"]


@pytest.mark.asyncio
async def test_create_requires_recipes_write(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user, scopes=["recipes:read"])
    before = _counts(user)

    with pytest.raises(McpToolError, match="recipes:write"):
        await create_recipe(name="Toast", ingredients=["1 slice bread"], instructions=["Toast it."])

    assert _counts(user) == before


@pytest.mark.asyncio
async def test_create_recipe_is_registered():
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}

    assert "create_recipe" in tools
    params = set(tools["create_recipe"].input_schema["properties"])
    assert params == {
        "name",
        "description",
        "servings",
        "yield_text",
        "prep_minutes",
        "cook_minutes",
        "total_minutes",
        "ingredients",
        "instructions",
        "tags",
        "categories",
        "tools",
        "notes",
        "source_url",
    }
    description = tools["create_recipe"].description or ""
    for hint in ("structured", "get_household_context", "add_mealplan_entries", "singular"):
        assert hint in description


def test_to_tool_error_formats_fields():
    with pytest.raises(ValidationError) as caught:
        RecipeCreateIn(name="", ingredients=[], instructions=[{"text": "Boil.", "timer_minutes": 0}])

    error = to_tool_error(caught.value)

    assert isinstance(error, McpToolError)
    message = str(error)
    assert "name:" in message
    assert "ingredients:" in message
    assert "instructions.0.timer_minutes:" in message
    assert "pydantic.dev" not in message
    assert isinstance(to_tool_error(ValueError("bad thing")), McpToolError)
    assert str(to_tool_error(ValueError("bad thing"))) == "bad thing"


# ---------------------------------------------------------------------- policy


def test_instructions_text():
    assert POLICY in INSTRUCTIONS
    assert "Always confirm" not in INSTRUCTIONS
    assert "get_household_context first" in INSTRUCTIONS


def _tool_functions() -> list[Callable[..., Any]]:
    modules = [m for _, m in inspect.getmembers(tools_package, inspect.ismodule)]
    assert recipe_write in modules
    return [fn for module in modules for _, fn in inspect.getmembers(module, inspect.iscoroutinefunction)]


def test_write_docstrings_follow_policy():
    docstrings = {fn.__name__: fn.__doc__ or "" for fn in _tool_functions()}

    assert "create_recipe" in docstrings and "update_household_profile" in docstrings
    assert [name for name, doc in docstrings.items() if "always confirm" in doc.lower()] == []
    assert "never infer allergies" in docstrings["update_household_profile"].lower()


def test_time_text_prefers_text_then_seconds():
    assert time_text("1 hour 5 min", 600) == "1 hour 5 min"  # scraped free text is kept as is
    assert time_text(None, 1500) == "25 minutes"
    assert time_text("", 60) == "1 minute"
    assert time_text(None, 5400) == "90 minutes"
    assert time_text(None, None) is None
    assert time_text(None, 0) is None
