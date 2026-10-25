import contextlib
import inspect
from collections.abc import Callable
from fractions import Fraction
from typing import Any
from uuid import uuid4

import httpx
import pytest
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealie.mcp import auth, context
from mealie.mcp import tools as tools_package
from mealie.mcp.errors import McpToolError
from mealie.mcp.server import INSTRUCTIONS, mcp_server
from mealie.mcp.tools import recipe_write
from mealie.mcp.tools._summaries import time_text
from mealie.mcp.tools.recipe_write import create_recipe, import_recipe_from_url, to_tool_error, update_recipe
from mealie.mcp.tools.recipes import get_recipe_impl
from mealie.pkgs import safehttp
from mealie.pkgs.safehttp.fetch import FetchResult
from mealie.repos.all_repositories import get_repositories
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_asset import RecipeAsset
from mealie.schema.recipe.recipe_category import TagSave
from mealie.schema.recipe.recipe_comments import RecipeCommentSave
from mealie.schema.recipe.recipe_ingredient import RecipeIngredient, SaveIngredientFood, SaveIngredientUnit
from mealie.schema.recipe.recipe_nutrition import Nutrition
from mealie.schema.recipe.recipe_step import IngredientReferences, NoteReference
from mealie.schema.response.pagination import PaginationQuery
from mealie.services.claude_context import recipe_writer as recipe_writer_module
from mealie.services.claude_context.recipe_writer import (
    IngredientIn,
    NoteIn,
    RecipeCreateIn,
    RecipeFieldsIn,
    RecipeWriter,
    StepIn,
)
from mealie.services.event_bus_service.event_types import EventTypes
from mealie.services.recipe import recipe_service as recipe_service_module
from mealie.services.recipe.recipe_data_service import RecipeDataService
from mealie.services.recipe.recipe_service import RecipeService
from mealie.services.recipe.recipe_web_import import normalise_source_url
from mealie.services.scraper import recipe_scraper as recipe_scraper_module
from tests import data as test_data
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


# ---------------------------------------------------------------------- nothing stays behind


@pytest.mark.asyncio
async def test_near_duplicate_new_organizers_create_one_each(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """ "Dinner", "Dinners" and "Dinnerr" are one organizer for Mealie's resolver; planning must agree."""
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    t = random_string(6)
    before = _counts(user)

    result = await create_recipe(
        name="Stew",
        ingredients=["1 onion"],
        instructions=["Simmer."],
        tags=[f"Dinner{t}", f"Dinners{t}", f"Dinnerr{t}"],
        categories=[f"Mains{t}", f"Main{t}"],
        tools=[f"Casserole{t}", f"Casseroles{t}"],
    )

    after = _counts(user)
    assert after["tags"] == before["tags"] + 1
    assert after["categories"] == before["categories"] + 1
    assert after["tools"] == before["tools"] + 1
    assert result["tags"] == [f"Dinner{t}"]
    assert result["categories"] == [f"Mains{t}"]
    assert result["tools"] == [f"Casserole{t}"]


@pytest.mark.asyncio
async def test_failed_save_removes_only_rows_this_call_created(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """Choice (b): if the save fails after apply(), the foods, units and organizers this call created
    are deleted, and rows that already existed are kept."""
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    existing_food = user.repos.ingredient_foods.create(
        SaveIngredientFood(name=random_string(10), group_id=user.group_id)
    )
    existing_tag = user.repos.tags.create(TagSave(name=random_string(10), group_id=user.group_id))
    before = _counts(user)

    def broken_create_one(self, recipe):
        raise IntegrityError("INSERT INTO recipes ...", {}, Exception("UNIQUE constraint failed: recipes.slug"))

    monkeypatch.setattr(RecipeService, "create_one", broken_create_one)

    with pytest.raises(McpToolError) as caught:
        await create_recipe(
            name="Soup",
            ingredients=[
                {"quantity": 1, "food": existing_food.name},
                {"quantity": 2, "unit": random_string(8), "food": random_string(10)},
                f"3 {random_string(9)}",
            ],
            instructions=["Cook."],
            tags=[existing_tag.name, random_string(10)],
            categories=[random_string(10)],
            tools=[random_string(10)],
        )

    message = str(caught.value)
    assert message.startswith("Mealie couldn't save the recipe: a database error")
    assert "INSERT" not in message and "UNIQUE" not in message
    session.expire_all()
    assert _counts(user) == before
    assert user.repos.ingredient_foods.get_one(existing_food.id) is not None
    assert user.repos.tags.get_one(existing_tag.id) is not None


@pytest.mark.asyncio
async def test_failures_after_the_save_return_the_recipe_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(recipe_write, "get_recipe_impl", broken)
    monkeypatch.setattr(RecipeWriter, "publish", broken)

    result = await create_recipe(name="Rice", ingredients=["1 cup rice"], instructions=["Boil."])

    assert set(result) == {"id", "name", "slug", "url", "warning"}
    assert "saved" in result["warning"] and "Don't create it again" in result["warning"]
    assert result["url"].endswith(f"/r/{result['slug']}")
    assert _stored(user, result["slug"]).name == "Rice"


# ---------------------------------------------------------------------- readable refusals


@pytest.mark.asyncio
async def test_non_finite_numbers_refused(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    before = _counts(user)

    with pytest.raises(McpToolError, match=r"ingredients\.0\.quantity: Input should be a finite number"):
        await create_recipe(name="X", ingredients=[{"quantity": float("inf"), "food": "egg"}], instructions=["Go."])
    with pytest.raises(McpToolError, match="servings: Input should be a finite number"):
        await create_recipe(name="X", ingredients=["1 egg"], instructions=["Go."], servings=float("nan"))

    assert _counts(user) == before


@pytest.mark.asyncio
async def test_wrong_argument_types_get_our_message(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """Through the SDK: the arguments reach RecipeCreateIn, not the SDK's own argument model."""
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    before = _counts(user)

    with pytest.raises(ToolError) as caught:
        await mcp_server.call_tool(
            "create_recipe",
            {"name": "X", "ingredients": [5], "instructions": ["Go."], "tags": "dinner", "cook_minutes": 5.5},
        )

    message = str(caught.value)
    assert "create_recipeArguments" not in message and "pydantic.dev" not in message
    assert "ingredients.0: expected a text line or an object" in message
    assert "tags: Input should be a valid list" in message
    assert "cook_minutes:" in message
    assert _counts(user) == before


@pytest.mark.asyncio
async def test_tool_schema_still_describes_the_shape():
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}
    schema = tools["create_recipe"].input_schema

    assert set(schema["required"]) == {"name", "ingredients", "instructions"}
    ingredients = schema["properties"]["ingredients"]
    assert ingredients["type"] == "array"
    object_item = next(item for item in ingredients["items"]["anyOf"] if item["type"] == "object")
    assert set(object_item["properties"]) == {"quantity", "unit", "food", "note", "section", "ref"}
    assert {"type": "null"} in schema["properties"]["servings"]["anyOf"]


def test_to_tool_error_keeps_unknown_keys_and_drops_union_noise():
    def message(**kwargs: Any) -> str:
        with pytest.raises(ValidationError) as caught:
            RecipeCreateIn(**kwargs)
        return str(to_tool_error(caught.value))

    base: dict[str, Any] = {"name": "Soup", "ingredients": ["1 egg"], "instructions": ["Cook."]}

    unknown = message(**{**base, "ingredients": [{"Quantity": 1, "food": "egg"}, {"str": 1, "food": "egg"}]})
    assert "ingredients.0.Quantity: Extra inputs are not permitted" in unknown
    assert "ingredients.1.str: Extra inputs are not permitted" in unknown
    assert "IngredientIn" not in unknown and "function-after" not in unknown

    step = message(**{**base, "instructions": [{"txt": "Boil."}]})
    assert "instructions.0.text: Field required" in step
    assert "instructions.0.txt: Extra inputs are not permitted" in step
    assert "valid string" not in step  # the plain-string branch didn't apply

    assert message(**{**base, "instructions": [7]}) == "instructions.0: expected a text line or an object"
    assert message(**{**base, "Colour": "red"}) == "Colour: Extra inputs are not permitted"


@pytest.mark.parametrize("name", ["!!!", "...", "🍅"])
def test_food_and_unit_names_must_have_a_letter_or_digit(name: str):
    with pytest.raises(ValidationError, match="food or unit name needs at least one letter or digit"):
        RecipeCreateIn(name="Soup", ingredients=[{"food": name}], instructions=["Cook."])
    with pytest.raises(ValidationError, match="food or unit name needs at least one letter or digit"):
        RecipeCreateIn(name="Soup", ingredients=[{"food": "egg", "unit": name}], instructions=["Cook."])


@pytest.mark.parametrize("bad", ["a\x00b", "a\x07b", "a\x0bb", "a\x0cb", "a\x1bb"])
def test_control_characters_refused(bad: str):
    base: dict[str, Any] = {"name": "Soup", "ingredients": ["1 egg"], "instructions": ["Cook."]}
    for override in (
        {"name": bad},
        {"description": bad},
        {"yield_text": bad},
        {"source_url": f"https://example.com/{bad}"},
        {"ingredients": [bad]},
        {"ingredients": [{"food": bad}]},
        {"ingredients": [{"food": "egg", "note": bad}]},
        {"instructions": [bad]},
        {"instructions": [{"text": "Boil.", "title": bad}]},
        {"notes": [{"title": "Tip", "text": bad}]},
        {"tags": [bad]},
    ):
        with pytest.raises(ValidationError, match="control characters"):
            RecipeCreateIn(**{**base, **override})

    allowed = RecipeCreateIn(**{**base, "instructions": ["Boil.\n\tThen drain."], "description": "a\tb\nc"})
    assert allowed.description == "a\tb\nc"


@pytest.mark.asyncio
async def test_punctuation_only_plain_line_is_kept_as_a_note(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    foods_before = _counts(user)["foods"]

    result = await create_recipe(name="Odd", ingredients=["!!!", "???"], instructions=["Look."])

    assert [i["food"] for i in result["ingredients"]] == [None, None]
    assert [i["note"] for i in result["ingredients"]] == ["!!!", "???"]
    assert _counts(user)["foods"] == foods_before


def test_time_text_never_says_zero_minutes():
    assert time_text(None, 30) == "1 minute"
    assert time_text(None, 1) == "1 minute"
    assert time_text(None, 89) == "1 minute"


def test_line_breaks_are_normalised():
    fields = RecipeCreateIn(
        name="Soup",
        description="one\r\ntwo\rthree",
        ingredients=["1 egg"],
        instructions=["Boil.\r\nThen drain.", {"text": "Serve\r\nhot.", "title": "End"}],
        notes=[{"title": "Tip", "text": "a\rb"}],
    )

    assert fields.description == "one\ntwo\nthree"
    assert fields.instructions[0] == "Boil.\nThen drain."
    step = fields.instructions[1]
    assert isinstance(step, StepIn) and step.text == "Serve\nhot."
    assert fields.notes is not None and fields.notes[0].text == "a\nb"


# ---------------------------------------------------------------------- partial saves and cleanup


@pytest.mark.asyncio
async def test_failure_after_the_recipe_is_committed_keeps_it(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """create_one commits the recipe, then adds the timeline event: if that fails, the recipe and the
    foods and organizers it uses stay, and the result says it was saved."""
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    food, tag = random_string(10), random_string(10)
    before = _counts(user)

    def broken_timeline_event(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("timeline down")

    monkeypatch.setattr(recipe_service_module, "RecipeTimelineEventCreate", broken_timeline_event)

    result = await create_recipe(
        name="Pilaf", ingredients=[{"quantity": 1, "food": food}], instructions=["Cook."], tags=[tag]
    )

    assert "saved" in result["warning"] and "Don't create it again" in result["warning"]
    assert result["slug"] and result["url"].endswith(f"/r/{result['slug']}")
    stored = _stored(user, result["slug"])
    assert [t.name for t in stored.tags or []] == [tag]
    assert stored.recipe_ingredient[0].food is not None and stored.recipe_ingredient[0].food.name == food
    after = _counts(user)
    assert (after["recipes"], after["foods"], after["tags"]) == (
        before["recipes"] + 1,
        before["foods"] + 1,
        before["tags"] + 1,
    )
    assert result["tags"] == [tag]  # the read-back still worked, so the full shape is returned


@pytest.mark.asyncio
async def test_a_failing_cleanup_delete_is_logged_and_the_error_stays_readable(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    unique_user_fn_scoped: TestUser,
    caplog: pytest.LogCaptureFixture,
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    before = _counts(user)
    tags_repo_class = type(user.repos.tags)
    real_delete = tags_repo_class.delete

    def flaky_delete(self, value, match_key=None):
        if self.model.__tablename__ == "tags":
            raise RuntimeError("tag delete failed")
        return real_delete(self, value, match_key)

    def broken_create_one(self, recipe):
        raise RuntimeError("disk full")

    monkeypatch.setattr(tags_repo_class, "delete", flaky_delete)
    monkeypatch.setattr(RecipeService, "create_one", broken_create_one)

    with pytest.raises(McpToolError, match="^Mealie couldn't save the recipe: disk full. Nothing was saved"):
        await create_recipe(
            name="Soup",
            ingredients=[{"quantity": 1, "food": random_string(10)}],
            instructions=["Cook."],
            tags=[random_string(10)],
            categories=[random_string(10)],
        )

    assert "Could not remove" in caplog.text
    session.expire_all()
    after = _counts(user)
    assert after["tags"] == before["tags"] + 1  # the one that couldn't be deleted (logged)
    assert {k: v for k, v in after.items() if k != "tags"} == {k: v for k, v in before.items() if k != "tags"}


# ---------------------------------------------------------------------- organizer matching


async def _new_tag_rows(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, tags: list[str]):
    _as_user(monkeypatch, session, user)
    before = _counts(user)["tags"]
    result = await create_recipe(name="Dish", ingredients=["1 egg"], instructions=["Cook."], tags=tags)
    return _counts(user)["tags"] - before, result["tags"]


@pytest.mark.asyncio
async def test_non_transitive_near_names_follow_the_plan(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """abcdefghij ~ abcdefghik and abcdefghik ~ abcdefghkk, but abcdefghij !~ abcdefghkk: the middle name
    folds into the first and the third stays separate, in the plan and in the database."""
    created, tags = await _new_tag_rows(
        monkeypatch, session, unique_user_fn_scoped, ["abcdefghij", "abcdefghik", "abcdefghkk"]
    )

    assert created == 2
    assert sorted(tags) == ["abcdefghij", "abcdefghkk"]


@pytest.mark.asyncio
async def test_accent_and_case_variants_are_one_organizer(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    t = random_string(6)
    created, tags = await _new_tag_rows(
        monkeypatch, session, unique_user_fn_scoped, [f"Crème{t}", f"CREME{t}", f"crème{t}"]
    )

    assert created == 1
    assert tags == [f"Crème{t}"]


@pytest.mark.asyncio
async def test_existing_organizer_plus_near_duplicates_creates_only_the_new_one(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    t = random_string(6)
    existing = user.repos.tags.create(TagSave(name=f"Dinner{t}", group_id=user.group_id))

    created, tags = await _new_tag_rows(monkeypatch, session, user, [f"Dinners{t}", f"Dinnerr{t}", f"Lunch{t}"])

    assert created == 1
    assert sorted(tags) == sorted([existing.name, f"Lunch{t}"])
    assert user.repos.tags.get_one(existing.id) is not None


# ---------------------------------------------------------------------- schema drift


@pytest.mark.asyncio
async def test_hand_written_schema_matches_the_models():
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}
    schema = tools["create_recipe"].input_schema

    assert set(schema["properties"]) == set(RecipeCreateIn.model_fields)
    assert set(schema["required"]) == {n for n, f in RecipeCreateIn.model_fields.items() if f.is_required()}

    def object_branch(prop: dict[str, Any]) -> dict[str, Any]:
        return next(item for item in prop["items"]["anyOf"] if item.get("type") == "object")

    ingredient = object_branch(schema["properties"]["ingredients"])
    step = object_branch(schema["properties"]["instructions"])
    note = next(item for item in schema["properties"]["notes"]["anyOf"] if item.get("type") == "array")["items"]
    for shown, model in ((ingredient, IngredientIn), (step, StepIn), (note, NoteIn)):
        assert set(shown["properties"]) == set(model.model_fields), model.__name__
        required = {n for n, f in model.model_fields.items() if f.is_required()}
        assert set(shown.get("required", [])) == required, model.__name__


# ---------------------------------------------------------------------- update

CANT_EDIT = (
    "You can't edit this recipe in Mealie (it is locked, or it belongs to another household that doesn't allow edits)."
)


async def _new_recipe(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser, **kwargs: Any) -> Recipe:
    """A recipe created through create_recipe as `user`; returns it as stored."""
    _as_user(monkeypatch, session, user)
    data: dict[str, Any] = {
        "name": f"Dish {random_string(6)}",
        "ingredients": ["200 g spaghetti"],
        "instructions": ["Cook."],
    }
    data.update(kwargs)
    result = await create_recipe(**data)
    return _stored(user, result["slug"])


def _snapshot(user: TestUser, recipe_id: Any) -> dict[str, Any]:
    """What a refused update must leave alone."""
    user.repos.session.expire_all()
    recipe = cross_group_recipes(user).get_one(recipe_id, "id")
    assert recipe is not None
    return recipe.model_dump(exclude={"updated_at", "update_at"})


def cross_group_recipes(user: TestUser):
    return get_repositories(user.repos.session, group_id=user.group_id, household_id=None).recipes


def _set_household_lock(user: TestUser, household_id: Any, locked: bool) -> None:
    household = user.repos.households.get_one(household_id)
    assert household and household.preferences
    household.preferences.lock_recipe_edits_from_other_households = locked
    user.repos.household_preferences.update(household.id, household.preferences)


@pytest.mark.asyncio
async def test_update_partial(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    tag = random_string(8)
    recipe = await _new_recipe(
        monkeypatch,
        session,
        user,
        ingredients=["200 g spaghetti", "salt to taste"],
        instructions=[{"text": "Boil.", "title": "Pasta", "timer_minutes": 9}],
        tags=[tag],
        servings=2,
    )
    user.repos.recipes.update_image(recipe.slug, "webp")
    image = _stored(user, recipe.slug).image
    assert image
    before = _stored(user, recipe.slug)

    result = await update_recipe(slug_or_id=recipe.slug, description="Now with a description.")

    after = _stored(user, recipe.slug)
    assert after.description == "Now with a description."
    assert after.name == before.name and after.slug == before.slug
    assert [i.display for i in after.recipe_ingredient] == [i.display for i in before.recipe_ingredient]
    assert [(s.title, s.text, s.duration_seconds) for s in after.recipe_instructions or []] == [("Pasta", "Boil.", 540)]
    assert [t.name for t in after.tags or []] == [tag]
    assert after.recipe_servings == 2
    assert after.image == image
    assert result["description"] == "Now with a description."
    assert result["not_scaled"] == []
    assert result["url"].endswith(f"/r/{recipe.slug}")


@pytest.mark.asyncio
async def test_update_by_id_and_rename(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user)
    new_name = f"Renamed {random_string(6)}"

    result = await update_recipe(slug_or_id=str(recipe.id), name=new_name)

    assert result["name"] == new_name and result["id"] == str(recipe.id)
    assert _stored(user, result["slug"]).name == new_name


@pytest.mark.asyncio
async def test_rename_onto_an_existing_name_is_refused(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    first = await _new_recipe(monkeypatch, session, user)
    second = await _new_recipe(monkeypatch, session, user)
    before = _counts(user)
    snapshot = _snapshot(user, second.id)

    with pytest.raises(McpToolError, match="already"):
        await update_recipe(slug_or_id=second.slug, name=first.name.upper(), tags=[random_string(8)])

    assert _counts(user) == before
    assert _snapshot(user, second.id) == snapshot


@pytest.mark.asyncio
async def test_update_replaces_lists(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(
        monkeypatch,
        session,
        user,
        ingredients=["200 g spaghetti", "2 eggs", "50 g pecorino"],
        instructions=["Boil.", "Mix."],
        tags=[random_string(8), random_string(8)],
        notes=[{"title": "Tip", "text": "Old tip."}],
    )
    # the UI links ingredients to steps: step 2 uses the eggs and the pecorino
    stored = _stored(user, recipe.slug)
    steps = stored.recipe_instructions or []
    steps[1].ingredient_references = [
        IngredientReferences(reference_id=stored.recipe_ingredient[1].reference_id),
        IngredientReferences(reference_id=stored.recipe_ingredient[2].reference_id),
    ]
    user.repos.recipes.update(stored.slug, stored)
    assert len((_stored(user, recipe.slug).recipe_instructions or [])[1].ingredient_references) == 2
    new_tag = random_string(8)

    result = await update_recipe(
        slug_or_id=recipe.slug,
        ingredients=[{"quantity": 400, "unit": "g", "food": "spaghetti"}, "1 clove garlic"],
        tags=[new_tag],
        notes=[],
    )

    after = _stored(user, recipe.slug)
    assert len(after.recipe_ingredient) == 2
    assert [t.name for t in after.tags or []] == [new_tag]
    assert after.notes == []
    # the steps were not sent: they stay, and their references to the removed ingredients are dropped
    assert [s.text for s in after.recipe_instructions or []] == ["Boil.", "Mix."]
    assert all(s.ingredient_references == [] for s in after.recipe_instructions or [])
    assert len(result["ingredients"]) == 2


@pytest.mark.asyncio
async def test_scale_to_servings(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(
        monkeypatch,
        session,
        user,
        servings=2,
        ingredients=[
            {"quantity": 200, "unit": "g", "food": "spaghetti"},
            {"food": "salt", "note": "to taste"},
            {"quantity": 0, "food": "pepper"},
            {"note": "a handful of basil"},
        ],
    )

    result = await update_recipe(slug_or_id=recipe.slug, scale_to_servings=4)

    after = _stored(user, recipe.slug)
    assert after.recipe_servings == 4
    assert [i.quantity for i in after.recipe_ingredient] == [400, None, 0, None]
    assert result["not_scaled"] == ["salt to taste", "pepper", "a handful of basil"]
    assert result["servings"] == 4
    assert result["ingredients"][0]["quantity"] == 400


@pytest.mark.asyncio
async def test_scale_has_no_float_noise(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(
        monkeypatch, session, user, servings=3, ingredients=[{"quantity": 1.5, "unit": "cup", "food": "rice"}]
    )

    await update_recipe(slug_or_id=recipe.slug, scale_to_servings=2)

    assert _stored(user, recipe.slug).recipe_ingredient[0].quantity == 1.0


@pytest.mark.asyncio
async def test_scale_refusals_write_nothing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    no_servings = await _new_recipe(monkeypatch, session, user)
    with_servings = await _new_recipe(monkeypatch, session, user, servings=2)
    before = _counts(user)
    snapshots = {r.id: _snapshot(user, r.id) for r in (no_servings, with_servings)}

    with pytest.raises(McpToolError, match="no servings"):
        await update_recipe(slug_or_id=no_servings.slug, scale_to_servings=4, tags=[random_string(8)])
    with pytest.raises(McpToolError, match="ingredients"):
        await update_recipe(
            slug_or_id=with_servings.slug, scale_to_servings=4, ingredients=[{"quantity": 1, "food": random_string(9)}]
        )
    with pytest.raises(McpToolError, match="servings"):
        await update_recipe(slug_or_id=with_servings.slug, scale_to_servings=4, servings=6)
    with pytest.raises(McpToolError, match="scale_to_servings"):
        await update_recipe(slug_or_id=with_servings.slug, scale_to_servings=0)

    assert _counts(user) == before
    assert {r_id: _snapshot(user, r_id) for r_id in snapshots} == snapshots


@pytest.mark.asyncio
async def test_servings_change_keeps_the_yield_quantity_in_step(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """The UI scales servings and yield quantity by the same factor; so do scale_to_servings and servings."""
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user, servings=4, yield_text="cookies")
    stored = _stored(user, recipe.slug)
    stored.recipe_yield_quantity = 12  # e.g. a scraped "12 cookies"
    user.repos.recipes.update(stored.slug, stored)

    await update_recipe(slug_or_id=recipe.slug, scale_to_servings=8)
    assert _stored(user, recipe.slug).recipe_yield_quantity == 24

    await update_recipe(slug_or_id=recipe.slug, servings=2)
    after = _stored(user, recipe.slug)
    assert (after.recipe_servings, after.recipe_yield_quantity) == (2, 6)
    assert after.recipe_yield_display == "6 cookies"

    # no yield quantity: nothing to keep in step
    plain = await _new_recipe(monkeypatch, session, user, servings=4)
    await update_recipe(slug_or_id=plain.slug, servings=6)
    assert _stored(user, plain.slug).recipe_yield_quantity == 0


@pytest.mark.asyncio
async def test_total_time_follows_its_parts_when_it_was_their_sum(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped

    summed = await _new_recipe(monkeypatch, session, user, prep_minutes=10, cook_minutes=20, total_minutes=30)
    await update_recipe(slug_or_id=summed.slug, cook_minutes=25)
    assert _stored(user, summed.slug).total_time_seconds == 35 * 60

    # a total with resting time in it was not the sum of its parts: it stays
    rested = await _new_recipe(monkeypatch, session, user, prep_minutes=10, cook_minutes=20, total_minutes=90)
    await update_recipe(slug_or_id=rested.slug, cook_minutes=25)
    assert _stored(user, rested.slug).total_time_seconds == 90 * 60

    # an explicit total wins
    await update_recipe(slug_or_id=summed.slug, prep_minutes=5, total_minutes=60)
    assert _stored(user, summed.slug).total_time_seconds == 60 * 60

    # no times at all: the parts sent become the total
    blank = await _new_recipe(monkeypatch, session, user)
    await update_recipe(slug_or_id=blank.slug, prep_minutes=15)
    stored = _stored(user, blank.slug)
    assert (stored.prep_time_seconds, stored.total_time_seconds) == (15 * 60, 15 * 60)

    # free-text times (scraped): nothing to add up, the total stays
    texts = await _new_recipe(monkeypatch, session, user)
    raw = _stored(user, texts.slug)
    raw.total_time, raw.prep_time = "1 hour", "15 min"
    user.repos.recipes.update(raw.slug, raw)
    await update_recipe(slug_or_id=texts.slug, cook_minutes=20)
    stored = _stored(user, texts.slug)
    assert (stored.total_time, stored.total_time_seconds) == ("1 hour", None)


@pytest.mark.asyncio
async def test_nothing_to_change_is_refused(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user)

    with pytest.raises(McpToolError, match="Nothing to change"):
        await update_recipe(slug_or_id=recipe.slug)


@pytest.mark.asyncio
async def test_refused_update_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user, servings=2)
    before = _counts(user)
    snapshot = _snapshot(user, recipe.id)

    with pytest.raises(McpToolError, match="servings"):
        await update_recipe(slug_or_id=recipe.slug, tags=[random_string(8)], servings=0)
    with pytest.raises(McpToolError, match=r"instructions\.0"):
        await update_recipe(
            slug_or_id=recipe.slug, ingredients=[{"quantity": 1, "food": random_string(9)}], instructions=[" "]
        )
    with pytest.raises(McpToolError, match="instructions"):
        await update_recipe(slug_or_id=recipe.slug, instructions=[])
    with pytest.raises(McpToolError, match="recipe not found"):
        await update_recipe(slug_or_id="no-such-recipe", tags=[random_string(8)])

    assert _counts(user) == before
    assert _snapshot(user, recipe.id) == snapshot


@pytest.mark.asyncio
async def test_update_permissions_locked_recipe(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, h2_user: TestUser
):
    """Another household allows edits, but its owner locked this recipe."""
    _set_household_lock(unique_user, h2_user.household_id, False)
    try:
        recipe = await _new_recipe(monkeypatch, session, h2_user)
        stored = _stored(h2_user, recipe.slug)
        assert stored.settings is not None
        stored.settings.locked = True
        h2_user.repos.recipes.update(stored.slug, stored)

        _as_user(monkeypatch, session, unique_user)
        before = _counts(unique_user)
        snapshot = _snapshot(unique_user, recipe.id)

        with pytest.raises(McpToolError) as caught:
            await update_recipe(slug_or_id=recipe.slug, description="mine now", tags=[random_string(8)])

        assert str(caught.value) == CANT_EDIT
        assert _counts(unique_user) == before
        assert _snapshot(unique_user, recipe.id) == snapshot
    finally:
        _set_household_lock(unique_user, h2_user.household_id, True)


@pytest.mark.parametrize("household_locks_edits", [True, False])
@pytest.mark.asyncio
async def test_update_permissions_other_household(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    unique_user: TestUser,
    h2_user: TestUser,
    household_locks_edits: bool,
):
    _set_household_lock(unique_user, h2_user.household_id, household_locks_edits)
    try:
        recipe = await _new_recipe(monkeypatch, session, h2_user)
        stored = _stored(h2_user, recipe.slug)
        assert stored.settings is not None
        stored.settings.locked = False
        h2_user.repos.recipes.update(stored.slug, stored)

        _as_user(monkeypatch, session, unique_user)
        before = _counts(unique_user)
        snapshot = _snapshot(unique_user, recipe.id)

        if household_locks_edits:
            with pytest.raises(McpToolError) as caught:
                await update_recipe(slug_or_id=recipe.slug, description="from next door", tags=[random_string(8)])
            assert str(caught.value) == CANT_EDIT
            assert _counts(unique_user) == before
            assert _snapshot(unique_user, recipe.id) == snapshot
        else:
            result = await update_recipe(slug_or_id=recipe.slug, description="from next door")
            assert result["description"] == "from next door"
            unique_user.repos.session.expire_all()
            updated = cross_group_recipes(unique_user).get_one(recipe.id, "id")
            assert updated is not None and updated.description == "from next door"
            assert str(updated.household_id) == str(h2_user.household_id)  # it stays theirs
            assert str(updated.user_id) == str(h2_user.user_id)
    finally:
        _set_household_lock(unique_user, h2_user.household_id, True)


@pytest.mark.asyncio
async def test_update_permissions_other_group(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser, g2_user: TestUser
):
    recipe = await _new_recipe(monkeypatch, session, g2_user)
    snapshot = _snapshot(g2_user, recipe.id)

    _as_user(monkeypatch, session, unique_user_fn_scoped)
    before = _counts(unique_user_fn_scoped)
    for key in (recipe.slug, str(recipe.id)):
        with pytest.raises(McpToolError, match=f"^recipe not found: {key}$"):
            await update_recipe(slug_or_id=key, description="hijack", tags=[random_string(8)])

    assert _counts(unique_user_fn_scoped) == before
    assert _snapshot(g2_user, recipe.id) == snapshot


@pytest.mark.asyncio
async def test_update_publishes_event(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user)
    calls: list[dict[str, Any]] = []

    class FakeBus:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dispatch(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(recipe_writer_module, "EventBusService", FakeBus)

    await update_recipe(slug_or_id=recipe.slug, description="Updated.")

    assert [c["event_type"] for c in calls] == [EventTypes.recipe_updated]
    assert calls[0]["document_data"].recipe_slug == recipe.slug


@pytest.mark.asyncio
async def test_update_requires_recipes_write(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user)
    snapshot = _snapshot(user, recipe.id)
    _as_user(monkeypatch, session, user, scopes=["recipes:read"])

    with pytest.raises(McpToolError, match="recipes:write"):
        await update_recipe(slug_or_id=recipe.slug, description="nope")

    assert _snapshot(user, recipe.id) == snapshot


@pytest.mark.asyncio
async def test_failed_update_that_did_not_land_removes_rows_this_call_created(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user, servings=2)
    before = _counts(user)
    snapshot = _snapshot(user, recipe.id)

    def broken_update(self, match_value, new_data):
        raise IntegrityError("UPDATE recipes ...", {}, Exception("constraint failed"))

    monkeypatch.setattr(type(cross_group_recipes(user)), "update", broken_update)

    with pytest.raises(McpToolError) as caught:
        await update_recipe(
            slug_or_id=recipe.slug,
            ingredients=[{"quantity": 1, "unit": random_string(8), "food": random_string(10)}],
            tags=[random_string(8)],
            categories=[random_string(8)],
        )

    message = str(caught.value)
    assert message.startswith("Mealie couldn't update the recipe: a database error")
    assert "Nothing was changed" in message and "UPDATE" not in message
    session.expire_all()
    assert _counts(user) == before
    assert _snapshot(user, recipe.id) == snapshot


@pytest.mark.asyncio
async def test_failed_update_that_landed_keeps_it_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """update_one commits, then checks the assets: if that fails, the change is saved and the rows it
    uses stay."""
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user, servings=2)
    food, tag = random_string(10), random_string(8)
    before = _counts(user)

    def broken_check_assets(self, recipe, original_slug):
        raise RuntimeError("assets folder gone")

    monkeypatch.setattr(RecipeService, "check_assets", broken_check_assets)

    result = await update_recipe(slug_or_id=recipe.slug, ingredients=[{"quantity": 1, "food": food}], tags=[tag])

    assert "updated" in result["warning"] and "Don't send the same update again" in result["warning"]
    stored = _stored(user, recipe.slug)
    assert [t.name for t in stored.tags or []] == [tag]
    assert stored.recipe_ingredient[0].food is not None and stored.recipe_ingredient[0].food.name == food
    after = _counts(user)
    assert (after["foods"], after["tags"]) == (before["foods"] + 1, before["tags"] + 1)
    assert result["tags"] == [tag]


@pytest.mark.asyncio
async def test_update_tool_schema_matches_the_models():
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}
    schema = tools["update_recipe"].input_schema

    assert set(schema["properties"]) == {"slug_or_id", "scale_to_servings", *RecipeFieldsIn.model_fields}
    assert schema["required"] == ["slug_or_id"]
    assert all("default" not in prop for prop in schema["properties"].values())  # UNSET has no JSON form
    ingredient = next(i for i in schema["properties"]["ingredients"]["anyOf"] if i.get("type") == "array")
    object_item = next(item for item in ingredient["items"]["anyOf"] if item["type"] == "object")
    assert set(object_item["properties"]) == set(IngredientIn.model_fields)
    steps = next(i for i in schema["properties"]["instructions"]["anyOf"] if i.get("type") == "array")
    step_item = next(item for item in steps["items"]["anyOf"] if item.get("type") == "object")
    assert set(step_item["properties"]) == set(StepIn.model_fields)


def test_writer_scale_treats_zero_and_none_as_no_quantity():
    recipe = Recipe(
        name="Soup",
        recipe_servings=2,
        recipe_yield_quantity=4,
        recipe_ingredient=[
            RecipeIngredient(quantity=0.667, note="cups of stock"),
            RecipeIngredient(quantity=0.0, note="salt to taste"),
            RecipeIngredient(quantity=None, note="pepper"),
        ],
    )

    scaled, not_scaled = RecipeWriter.scale(recipe, 3)

    assert [i.quantity for i in scaled.recipe_ingredient] == [1.0, 0.0, None]
    assert not_scaled == ["salt to taste", "pepper"]
    assert (scaled.recipe_servings, scaled.recipe_yield_quantity) == (3, 6)
    assert recipe.recipe_servings == 2  # the input is left alone


@pytest.mark.parametrize(
    ("quantity", "factor", "expected"),
    [
        (0.667, Fraction(3, 2), 1.0),  # stored 2/3
        (1.5, Fraction(2, 3), 1.0),
        (0.333, Fraction(3), 1.0),  # stored 1/3
        (200, Fraction(2), 400),
        (0.1, Fraction(3), 0.3),
        (1.234, Fraction(1), 1.234),  # not near a kitchen fraction: kept as is
        (0.0625, Fraction(2), 0.125),
        (2.5, Fraction(4, 3), 3.333),
    ],
)
def test_scaled_quantity_has_no_float_noise(quantity: float, factor: Fraction, expected: float):
    assert recipe_writer_module._scaled_quantity(quantity, factor) == expected


# ---------------------------------------------------------------------- update keeps what get_recipe can't show


async def _linked_recipe(monkeypatch: pytest.MonkeyPatch, session: Session, user: TestUser) -> dict[str, Any]:
    """A recipe with a section, step timers, step-to-ingredient links and a note linked from a step;
    returns get_recipe's view of it."""
    recipe = await _new_recipe(
        monkeypatch,
        session,
        user,
        servings=2,
        ingredients=[
            {"quantity": 200, "unit": "g", "food": "spaghetti", "section": "Pasta"},
            {"quantity": 2, "food": "egg", "section": "Sauce"},
            {"quantity": 50, "unit": "g", "food": "pecorino"},
        ],
        instructions=[
            {"text": "Boil the spaghetti.", "timer_minutes": 9},
            {"text": "Whisk the eggs and pecorino.", "timer_minutes": 2},
            {"text": "Toss off the heat.", "timer_minutes": 1},
        ],
        notes=[{"title": "Tip", "text": "Keep pasta water."}],
    )
    stored = _stored(user, recipe.slug)
    pasta, egg, cheese = (i.reference_id for i in stored.recipe_ingredient)
    steps = stored.recipe_instructions or []
    steps[0].ingredient_references = [IngredientReferences(reference_id=pasta)]
    steps[1].ingredient_references = [IngredientReferences(reference_id=egg), IngredientReferences(reference_id=cheese)]
    steps[2].ingredient_references = [IngredientReferences(reference_id=pasta)]
    steps[2].note_references = [NoteReference(reference_id=(stored.notes or [])[0].reference_id)]
    user.repos.recipes.update(stored.slug, stored)
    with context.mcp_context() as ctx:
        return get_recipe_impl(ctx, recipe.slug)


def _links(user: TestUser, slug: str) -> list[tuple[str, int | None, list[str], int]]:
    """Per step: text, timer seconds, the foods it uses, and its number of note links."""
    stored = _stored(user, slug)
    food_by_ref = {i.reference_id: i.food.name if i.food else i.note for i in stored.recipe_ingredient}
    return [
        (
            s.text,
            s.duration_seconds,
            [food_by_ref.get(r.reference_id, "?") for r in s.ingredient_references],
            len(s.note_references),
        )
        for s in stored.recipe_instructions or []
    ]


LINKED = [
    ("Boil the spaghetti.", 540, ["spaghetti"], 0),
    ("Whisk the eggs and pecorino.", 120, ["egg", "pecorino"], 0),
    ("Toss off the heat.", 60, ["spaghetti"], 1),
]


@pytest.mark.asyncio
async def test_get_recipe_shows_refs_sections_timers_and_uses(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    view = await _linked_recipe(monkeypatch, session, unique_user_fn_scoped)

    refs = [i["ref"] for i in view["ingredients"]]
    assert [i["section"] for i in view["ingredients"]] == ["Pasta", "Sauce", None]
    assert [s["timer_minutes"] for s in view["instructions"]] == [9, 2, 1]
    assert [s["uses"] for s in view["instructions"]] == [[refs[0]], [refs[1], refs[2]], [refs[0]]]


@pytest.mark.asyncio
async def test_a_typo_fix_in_one_step_keeps_every_timer_and_link(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    first, second, third = view["instructions"]

    await update_recipe(
        slug_or_id=view["slug"],
        instructions=[
            first["text"],  # unchanged, as a plain string
            {"text": "Whisk the eggs and the pecorino.", "timer_minutes": 2, "uses": second["uses"]},  # the fix
            {"text": third["text"]},  # unchanged, as an object without timer or uses
        ],
    )

    assert _links(user, view["slug"]) == [
        LINKED[0],
        ("Whisk the eggs and the pecorino.", 120, ["egg", "pecorino"], 0),
        LINKED[2],
    ]


@pytest.mark.asyncio
async def test_replacing_ingredients_keeps_links_to_the_lines_kept_by_ref(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    pasta = view["ingredients"][0]

    await update_recipe(
        slug_or_id=view["slug"],
        # more spaghetti (same ref), the eggs and cheese replaced by cream
        ingredients=[{"ref": pasta["ref"], "quantity": 300, "unit": "g", "food": "spaghetti"}, "100 ml cream"],
    )

    stored = _stored(user, view["slug"])
    assert str(stored.recipe_ingredient[0].reference_id) == pasta["ref"]
    assert stored.recipe_ingredient[0].quantity == 300
    assert stored.recipe_ingredient[0].title == "Pasta"  # section kept: not sent
    assert [step[2] for step in _links(user, view["slug"])] == [["spaghetti"], [], ["spaghetti"]]


@pytest.mark.asyncio
async def test_plain_display_lines_sent_back_keep_the_links(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    lines = [i["display"] for i in view["ingredients"]]

    await update_recipe(slug_or_id=view["slug"], ingredients=[*lines, "1 pinch black pepper"])

    stored = _stored(user, view["slug"])
    assert [str(i.reference_id) for i in stored.recipe_ingredient[:3]] == [i["ref"] for i in view["ingredients"]]
    assert [i.title for i in stored.recipe_ingredient] == ["Pasta", "Sauce", None, None]
    assert _links(user, view["slug"]) == LINKED


@pytest.mark.asyncio
async def test_sections_survive_a_resend_without_them(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """Structured lines without ref that match one old line (same food, unit and quantity) keep its
    identity and section; a section sent as null clears it."""
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)

    await update_recipe(
        slug_or_id=view["slug"],
        ingredients=[
            {"quantity": 200, "unit": "g", "food": "spaghetti"},
            {"quantity": 2, "food": "egg", "section": None},
            {"quantity": 50, "unit": "g", "food": "pecorino"},
        ],
    )

    stored = _stored(user, view["slug"])
    assert [i.title for i in stored.recipe_ingredient] == ["Pasta", None, None]
    assert _links(user, view["slug"]) == LINKED


@pytest.mark.asyncio
async def test_a_kept_line_keeps_its_sub_recipe_link(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    dough = await _new_recipe(monkeypatch, session, user, name=f"Dough {random_string(6)}")
    pizza = await _new_recipe(
        monkeypatch, session, user, ingredients=[{"quantity": 1, "note": "pizza dough"}, "100 g mozzarella"]
    )
    stored = _stored(user, pizza.slug)
    stored.recipe_ingredient[0].referenced_recipe = dough
    user.repos.recipes.update(stored.slug, stored)
    with context.mcp_context() as ctx:
        view = get_recipe_impl(ctx, pizza.slug)
    dough_line, cheese = view["ingredients"]

    # by ref
    await update_recipe(
        slug_or_id=pizza.slug,
        ingredients=[{"ref": dough_line["ref"], "quantity": 2, "note": "pizza dough"}, cheese["display"]],
    )
    stored = _stored(user, pizza.slug)
    assert stored.recipe_ingredient[0].referenced_recipe is not None
    assert stored.recipe_ingredient[0].referenced_recipe.id == dough.id

    # as get_recipe's display line
    with context.mcp_context() as ctx:
        view = get_recipe_impl(ctx, pizza.slug)
    await update_recipe(slug_or_id=pizza.slug, ingredients=[i["display"] for i in view["ingredients"]])
    stored = _stored(user, pizza.slug)
    assert stored.recipe_ingredient[0].referenced_recipe is not None
    assert stored.recipe_ingredient[0].referenced_recipe.id == dough.id


@pytest.mark.asyncio
async def test_notes_matched_by_title_keep_the_step_links(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)

    await update_recipe(slug_or_id=view["slug"], notes=[{"title": "tip", "text": "Keep a cup of pasta water."}])
    assert [step[3] for step in _links(user, view["slug"])] == [0, 0, 1]

    await update_recipe(slug_or_id=view["slug"], notes=[{"title": "Serving", "text": "Warm plates."}])
    assert [step[3] for step in _links(user, view["slug"])] == [0, 0, 0]


@pytest.mark.asyncio
async def test_unmatched_lines_start_fresh_and_unknown_refs_are_dropped(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)

    await update_recipe(
        slug_or_id=view["slug"],
        ingredients=[{"ref": "not-a-ref", "quantity": 1, "food": "rice"}],
        instructions=[{"text": "Cook the rice.", "uses": ["not-a-uuid", str(uuid4())]}],
    )

    stored = _stored(user, view["slug"])
    assert str(stored.recipe_ingredient[0].reference_id) not in {i["ref"] for i in view["ingredients"]}
    assert _links(user, view["slug"]) == [("Cook the rice.", None, [], 0)]


@pytest.mark.asyncio
async def test_reordered_steps_keep_their_timers_and_links(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)

    await update_recipe(slug_or_id=view["slug"], instructions=[s["text"] for s in reversed(view["instructions"])])

    assert _links(user, view["slug"]) == list(reversed(LINKED))


@pytest.mark.asyncio
async def test_identical_display_lines_are_claimed_in_order(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(
        monkeypatch,
        session,
        user,
        ingredients=[{"quantity": 1, "food": "egg"}, {"quantity": 1, "food": "egg"}, "100 g flour"],
        instructions=["Beat one egg.", "Fold in the other egg."],
    )
    stored = _stored(user, recipe.slug)
    first_egg, second_egg, _flour = (i.reference_id for i in stored.recipe_ingredient)
    steps = stored.recipe_instructions or []
    steps[0].ingredient_references = [IngredientReferences(reference_id=first_egg)]
    steps[1].ingredient_references = [IngredientReferences(reference_id=second_egg)]
    user.repos.recipes.update(stored.slug, stored)
    with context.mcp_context() as ctx:
        view = get_recipe_impl(ctx, recipe.slug)
    lines = [i["display"] for i in view["ingredients"]]
    assert lines[0] == lines[1]

    await update_recipe(slug_or_id=recipe.slug, ingredients=[*lines, "1 pinch salt"])

    stored = _stored(user, recipe.slug)
    assert [i.reference_id for i in stored.recipe_ingredient[:2]] == [first_egg, second_egg]
    assert [[r.reference_id for r in s.ingredient_references] for s in stored.recipe_instructions or []] == [
        [first_egg],
        [second_egg],
    ]


@pytest.mark.asyncio
async def test_a_ref_or_uses_from_another_recipe_does_not_link(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    other = await _new_recipe(monkeypatch, session, user)
    foreign = view["ingredients"][0]["ref"]
    snapshot = _snapshot(user, view["id"])

    await update_recipe(
        slug_or_id=other.slug,
        ingredients=[{"ref": foreign, "quantity": 100, "unit": "g", "food": "spaghetti"}],
        instructions=[{"text": "Boil.", "uses": [foreign]}],
    )

    stored = _stored(user, other.slug)
    assert str(stored.recipe_ingredient[0].reference_id) != foreign
    assert _links(user, other.slug) == [("Boil.", None, [], 0)]
    assert _snapshot(user, view["id"]) == snapshot


@pytest.mark.asyncio
async def test_the_same_ref_sent_twice_keeps_one_identity(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    ref = view["ingredients"][0]["ref"]

    await update_recipe(
        slug_or_id=view["slug"],
        ingredients=[
            {"ref": ref, "quantity": 200, "unit": "g", "food": "spaghetti"},
            {"ref": ref, "quantity": 100, "unit": "g", "food": "linguine"},
        ],
    )

    first, second = _stored(user, view["slug"]).recipe_ingredient
    assert str(first.reference_id) == ref
    assert second.reference_id != first.reference_id
    assert [step[2] for step in _links(user, view["slug"])] == [["spaghetti"], [], ["spaghetti"]]


@pytest.mark.asyncio
async def test_a_slightly_changed_step_loses_its_links_unless_uses_is_sent(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    texts = [s["text"] for s in view["instructions"]]

    await update_recipe(slug_or_id=view["slug"], instructions=["Boil the spaghetti!", *texts[1:]])
    assert _links(user, view["slug"])[0] == ("Boil the spaghetti!", None, [], 0)

    first = view["instructions"][0]
    await update_recipe(
        slug_or_id=view["slug"],
        instructions=[{"text": "Boil the spaghetti well.", "timer_minutes": 9, "uses": first["uses"]}, *texts[1:]],
    )
    assert _links(user, view["slug"]) == [("Boil the spaghetti well.", 540, ["spaghetti"], 0), *LINKED[1:]]


@pytest.mark.asyncio
async def test_null_timer_removes_it_and_an_omitted_timer_stays(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    texts = [s["text"] for s in view["instructions"]]

    await update_recipe(
        slug_or_id=view["slug"],
        instructions=[{"text": texts[0], "timer_minutes": None}, {"text": texts[1]}, texts[2]],
    )
    assert [step[1] for step in _links(user, view["slug"])] == [None, 120, 60]
    assert [step[2] for step in _links(user, view["slug"])] == [s[2] for s in LINKED]  # links kept

    # through the SDK, as Claude sends it
    await mcp_server.call_tool(
        "update_recipe",
        {"slug_or_id": view["slug"], "instructions": [texts[0], {"text": texts[1], "timer_minutes": None}, texts[2]]},
    )
    assert [step[1] for step in _links(user, view["slug"])] == [None, None, 60]


@pytest.mark.asyncio
async def test_create_ignores_ref_and_uses(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    foreign = view["ingredients"][0]["ref"]

    recipe = await _new_recipe(
        monkeypatch,
        session,
        user,
        ingredients=[
            {"ref": foreign, "quantity": 1, "food": "rice"},
            {"ref": str(uuid4()), "quantity": 2, "food": "egg"},
        ],
        instructions=[{"text": "Cook.", "uses": [foreign]}],
    )

    stored = _stored(user, recipe.slug)
    assert str(stored.recipe_ingredient[0].reference_id) != foreign
    assert _links(user, recipe.slug) == [("Cook.", None, [], 0)]


# ---------------------------------------------------------------------- scaling limits


def test_scaling_down_never_turns_a_quantity_into_zero():
    recipe = Recipe(
        name="Paella",
        recipe_servings=6,
        recipe_ingredient=[
            RecipeIngredient(quantity=0.66, note="g saffron"),
            RecipeIngredient(quantity=2.48, note="cups flour"),
            RecipeIngredient(quantity=0.04, note="g vanilla"),
        ],
    )

    scaled, _ = RecipeWriter.scale(recipe, 0.01)

    # 0.66 x 0.01/6 = 0.0011 and 2.48 x 0.01/6 = 0.004133: 3 significant figures, not 0.001 and 0.004
    assert [i.quantity for i in scaled.recipe_ingredient][:2] == [0.0011, 0.00413]
    # 0.04 x 0.01/6 = 0.0000667: Mealie keeps 3 decimals, so the smallest amount it can store
    assert scaled.recipe_ingredient[2].quantity == 0.001


@pytest.mark.asyncio
async def test_a_tiny_scaled_quantity_is_stored_non_zero(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(
        monkeypatch, session, user, servings=6, ingredients=[{"quantity": 0.66, "unit": "g", "food": "saffron"}]
    )

    result = await update_recipe(slug_or_id=recipe.slug, scale_to_servings=0.01)

    quantity = _stored(user, recipe.slug).recipe_ingredient[0].quantity
    assert quantity is not None and quantity > 0
    assert result["not_scaled"] == []


@pytest.mark.asyncio
async def test_quantity_and_servings_limits_and_overflow(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user, servings=2)

    with pytest.raises(McpToolError, match=r"ingredients\.0\.quantity"):
        await update_recipe(slug_or_id=recipe.slug, ingredients=[{"quantity": 100001, "food": "rice"}])
    with pytest.raises(McpToolError, match="servings"):
        await update_recipe(slug_or_id=recipe.slug, servings=0.001)
    with pytest.raises(McpToolError, match="scale_to_servings"):
        await update_recipe(slug_or_id=recipe.slug, scale_to_servings=0.001)

    # a stored quantity beyond the input limits (older data) can't be scaled past the float range
    stored = _stored(user, recipe.slug)
    stored.recipe_ingredient[0].quantity = 1e308
    stored.recipe_servings = 0.01
    user.repos.recipes.update(stored.slug, stored)
    snapshot = _snapshot(user, recipe.id)

    with pytest.raises(McpToolError, match="too large"):
        await update_recipe(slug_or_id=recipe.slug, scale_to_servings=100)
    assert _snapshot(user, recipe.id) == snapshot


# ---------------------------------------------------------------------- null clears, omitted keeps


@pytest.mark.asyncio
async def test_null_clears_a_scalar_and_omitted_keeps_it(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(
        monkeypatch,
        session,
        user,
        description="Old.",
        yield_text="plates",
        prep_minutes=10,
        cook_minutes=20,
        total_minutes=45,
        source_url="https://example.com/r",
        servings=2,
    )

    await update_recipe(slug_or_id=recipe.slug, description=None, prep_minutes=None, source_url=None)

    stored = _stored(user, recipe.slug)
    assert (stored.description, stored.prep_time_seconds, stored.org_url) == (None, None, None)
    # omitted fields stay
    assert (stored.recipe_yield, stored.perform_time_seconds, stored.total_time_seconds) == ("plates", 1200, 2700)
    assert stored.recipe_servings == 2

    # through the SDK, as Claude sends it: an explicit null, other parameters absent
    await mcp_server.call_tool("update_recipe", {"slug_or_id": recipe.slug, "yield_text": None})
    stored = _stored(user, recipe.slug)
    assert (stored.recipe_yield, stored.perform_time_seconds) == (None, 1200)


@pytest.mark.asyncio
async def test_null_is_refused_for_names_lists_and_servings(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user, servings=2)
    snapshot = _snapshot(user, recipe.id)

    for field in ("name", "servings", "ingredients", "instructions", "tags", "notes", "scale_to_servings"):
        with pytest.raises(McpToolError, match=f"{field} can't be null"):
            await update_recipe(slug_or_id=recipe.slug, **{field: None})

    assert _snapshot(user, recipe.id) == snapshot


# ---------------------------------------------------------------------- more update coverage


@pytest.mark.asyncio
async def test_partial_update_keeps_everything_else(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    view = await _linked_recipe(monkeypatch, session, user)
    stored = _stored(user, view["slug"])
    assert stored.settings is not None
    stored.settings.show_nutrition = True
    stored.settings.public = True
    stored.nutrition = Nutrition(calories="640", protein_content="24")
    stored.assets = [RecipeAsset(name="Card", icon="mdi-file", file_name="card.pdf")]
    stored.extras = {"origin": "Rome"}
    stored.rating = 4.5
    stored.recipe_yield_quantity = 2
    user.repos.recipes.update(stored.slug, stored)
    user.repos.comments.create(RecipeCommentSave(recipe_id=stored.id, text="Lovely.", user_id=user.user_id))
    user.repos.recipes.update_image(stored.slug, "webp")

    def full(slug: str) -> dict[str, Any]:
        data = _stored(user, slug).model_dump(exclude={"description", "date_updated", "updated_at"})
        for step in data["recipe_instructions"]:
            step.pop("id")  # every update rewrites the step rows, as in the UI
        return data

    before = full(view["slug"])

    await update_recipe(slug_or_id=view["slug"], description="Changed only this.")

    assert full(view["slug"]) == before
    assert _stored(user, view["slug"]).description == "Changed only this."


@pytest.mark.asyncio
async def test_rename_that_only_changes_case(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user, name=f"tomato soup {random_string(6)}")

    result = await update_recipe(slug_or_id=recipe.slug, name=recipe.name.title())

    assert result["slug"] == recipe.slug
    assert _stored(user, recipe.slug).name == recipe.name.title()


@pytest.mark.asyncio
async def test_failure_inside_apply_leaves_nothing_behind(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """apply() creates the new food, then fails on the unit: the food is removed again."""
    user = unique_user_fn_scoped
    recipe = await _new_recipe(monkeypatch, session, user)
    before = _counts(user)
    snapshot = _snapshot(user, recipe.id)

    def broken_create_unit(self, name, created):
        raise RuntimeError("unit table locked")

    monkeypatch.setattr(RecipeWriter, "_create_unit", broken_create_unit)

    with pytest.raises(
        McpToolError, match="^Mealie couldn't update the recipe: unit table locked. Nothing was changed"
    ):
        await update_recipe(
            slug_or_id=recipe.slug,
            ingredients=[{"quantity": 1, "unit": random_string(8), "food": random_string(10)}],
            tags=[random_string(8)],
        )

    session.expire_all()
    assert _counts(user) == before
    assert _snapshot(user, recipe.id) == snapshot


# ---------------------------------------------------------------------- import_recipe_from_url


def _serve(monkeypatch: pytest.MonkeyPatch, html: str) -> list[str]:
    """The scraper's fetch returns `html` for any URL (no network) and no image is downloaded;
    returns the list of URLs fetched."""
    fetched: list[str] = []

    async def fake_fetch(url: str, **_: Any) -> FetchResult:
        fetched.append(url)
        return FetchResult(html.encode(), 200, url, httpx.Headers(), "utf-8")

    async def no_image(self: RecipeDataService, *_: Any) -> None:
        return None

    monkeypatch.setattr(recipe_scraper_module, "resilient_fetch", fake_fetch)
    monkeypatch.setattr(RecipeDataService, "scrape_image", no_image)
    return fetched


def _fail_fetch(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    async def failing_fetch(url: str, **_: Any) -> FetchResult:
        raise exc

    monkeypatch.setattr(recipe_scraper_module, "resilient_fetch", failing_fetch)


def _page_url() -> str:
    return f"https://www.example.com/recipes/{random_string(8)}"


class _EventLog:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[dict[str, Any]] = []
        log = self

        class FakeBus:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def dispatch(self, **kwargs: Any) -> None:
                log.calls.append(kwargs)

        monkeypatch.setattr(recipe_writer_module, "EventBusService", FakeBus)


PIZZA = test_data.html_detroit_style_pepperoni_pizza
CHICKEN = test_data.html_taiwanese_three_cup_chicken_san_bei_gi_recipe


def _json_ld_page(recipe: dict[str, Any]) -> str:
    import json

    data = {"@context": "https://schema.org", "@type": "Recipe", **recipe}
    return f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head><body></body></html>'


@pytest.mark.asyncio
async def test_import_success(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    fetched = _serve(monkeypatch, PIZZA.read_text())
    events = _EventLog(monkeypatch)
    url = _page_url()

    result = await import_recipe_from_url(url=url)

    assert fetched == [url]
    assert result["already_existed"] is False
    assert result["name"] == "Detroit-Style Pepperoni Pizza"
    assert result["org_url"] == url
    stored = _stored(user, result["slug"])
    assert str(stored.user_id) == str(user.user_id)
    assert str(stored.household_id) == str(user.household_id)
    assert len(stored.recipe_ingredient) == 8 and len(stored.recipe_instructions or []) == 5
    # parsed into food and unit where possible, the rest kept as notes with the original line
    by_food = {i.food.name: i for i in stored.recipe_ingredient if i.food is not None}
    assert "pepperoni" in by_food
    pepperoni = by_food["pepperoni"]
    assert pepperoni.quantity == 4 and pepperoni.unit is not None
    assert all(i.original_text for i in stored.recipe_ingredient)
    assert len(by_food) >= 5
    # include_tags defaults to true: the page's 12 tags
    assert len(stored.tags or []) == 12
    assert [c["event_type"] for c in events.calls] == [EventTypes.recipe_created]
    assert events.calls[0]["document_data"].recipe_slug == result["slug"]


@pytest.mark.asyncio
async def test_import_without_tags_and_bare_yield_becomes_servings(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    _serve(monkeypatch, CHICKEN.read_text())
    before = _counts(user)

    result = await import_recipe_from_url(url=_page_url(), include_tags=False)

    stored = _stored(user, result["slug"])
    # the page says "recipeYield": "6": schema.org's servings, so the recipe can be scaled
    assert (stored.recipe_servings, stored.recipe_yield_quantity) == (6, 0)
    assert result["servings"] == 6
    assert stored.tags == [] and _counts(user)["tags"] == before["tags"]


@pytest.mark.asyncio
async def test_import_dedup(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    fetched = _serve(monkeypatch, CHICKEN.read_text())
    url = _page_url()

    first = await import_recipe_from_url(url=url)
    recipes = _counts(user)["recipes"]

    for again in (f"{url}/", f"{url}#step-2", url.replace("https://www.example.com", "HTTPS://WWW.Example.COM")):
        result = await import_recipe_from_url(url=again)
        assert result["already_existed"] is True, again
        assert result["id"] == first["id"]
    assert _counts(user)["recipes"] == recipes
    assert fetched == [url]  # nothing fetched for a page already imported

    other_page = await import_recipe_from_url(url=f"{url}?page=2")
    assert other_page["already_existed"] is False
    assert other_page["id"] != first["id"]
    assert _counts(user)["recipes"] == recipes + 1

    # an older recipe whose source was stored un-normalised
    path = random_string(8)
    older = await create_recipe(
        name="Older", ingredients=["1 egg"], instructions=["Cook."], source_url=f"HTTPS://Example.com/{path}/"
    )
    result = await import_recipe_from_url(url=f"https://example.com/{path}")
    assert result["already_existed"] is True
    assert result["id"] == older["id"]
    assert len(fetched) == 2


@pytest.mark.asyncio
async def test_import_dedup_is_group_wide(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user: TestUser, h2_user: TestUser, g2_user: TestUser
):
    """A page another household of the group imported is returned, not imported again; another
    group's import isn't seen."""
    _serve(monkeypatch, CHICKEN.read_text())
    url = _page_url()
    _as_user(monkeypatch, session, h2_user)
    theirs = await import_recipe_from_url(url=url)

    _as_user(monkeypatch, session, unique_user)
    mine = await import_recipe_from_url(url=url)
    assert mine["already_existed"] is True and mine["id"] == theirs["id"]

    _as_user(monkeypatch, session, g2_user)
    other_group = await import_recipe_from_url(url=url)
    assert other_group["already_existed"] is False and other_group["id"] != theirs["id"]


def test_normalise_source_url():
    assert normalise_source_url("HTTPS://Example.com/r/") == "https://example.com/r"
    assert normalise_source_url(" https://example.com/r#x ") == "https://example.com/r"
    assert normalise_source_url("https://example.com/R/") == "https://example.com/R"  # paths keep their case
    assert normalise_source_url("https://example.com/r/?page=2#x") == "https://example.com/r?page=2"
    assert normalise_source_url("https://example.com/") == "https://example.com"


@pytest.mark.asyncio
async def test_import_errors(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    before = _counts(user)

    # not a web link: refused before anything is fetched
    for bad in ("ftp://example.com/r", "file:///etc/passwd", "javascript:alert(1)", "example.com/r", "", "https://"):
        with pytest.raises(McpToolError, match="url must be a web link"):
            await import_recipe_from_url(url=bad)

    # no recipe on the page
    _serve(monkeypatch, "<html><head><title>Hello</title></head><body><p>Just a blog.</p></body></html>")
    with pytest.raises(McpToolError, match="No recipe found on that page"):
        await import_recipe_from_url(url=_page_url())

    # unreachable: the connection fails, or the host doesn't resolve
    _fail_fetch(monkeypatch, httpx.ConnectError("connection refused"))
    with pytest.raises(McpToolError, match="Couldn't reach www.example.com: the site didn't answer"):
        await import_recipe_from_url(url=_page_url())
    _fail_fetch(monkeypatch, safehttp.InvalidDomainError("could not resolve host: nowhere.invalid"))
    with pytest.raises(McpToolError, match="Couldn't reach nowhere.invalid"):
        await import_recipe_from_url(url="https://nowhere.invalid/r")
    _fail_fetch(monkeypatch, safehttp.ForceTimeoutException())
    with pytest.raises(McpToolError, match="Couldn't reach"):
        await import_recipe_from_url(url=_page_url())

    assert _counts(user) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://127.0.0.1/recipe", "http://10.1.2.3/r", "http://[::1]:8080/r"])
async def test_import_blocked_address(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser, url: str
):
    """The real fetch (not patched): Mealie's SSRF guard refuses a private address before connecting,
    on the tool's worker-thread event loop, and the tool reports it."""
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    before = _counts(user)

    with pytest.raises(McpToolError, match="won't fetch that link"):
        await import_recipe_from_url(url=url)

    assert _counts(user) == before


@pytest.mark.asyncio
async def test_import_real_client_on_the_worker_loop(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    """The real curl-based client (only the address allow-list is widened to loopback) fetches a
    recorded page from a local server, on the event loop `run_in_context` starts in its worker
    thread. Twice, so a second fresh loop works too. No outside network: the server is local."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from mealie.core.config import get_app_settings
    from mealie.pkgs.safehttp import fetch as fetch_module

    page = CHICKEN.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        settings = get_app_settings().model_copy(update={"HTTP_ALLOW_LIST": "127.0.0.1"})
        monkeypatch.setattr(fetch_module, "get_app_settings", lambda: settings)

        async def no_image(self: RecipeDataService, *_: Any) -> None:
            return None

        monkeypatch.setattr(RecipeDataService, "scrape_image", no_image)
        user = unique_user_fn_scoped
        _as_user(monkeypatch, session, user)
        port = server.server_address[1]

        first = await import_recipe_from_url(url=f"http://127.0.0.1:{port}/three-cup-chicken")
        second = await import_recipe_from_url(url=f"http://127.0.0.1:{port}/three-cup-chicken?again=1")
    finally:
        server.shutdown()
        server.server_close()

    assert first["name"] == "Taiwanese Three Cup Chicken (San Bei Ji) Recipe"
    assert second["name"] == f"{first['name']} (1)"
    assert first["already_existed"] is False and second["already_existed"] is False


@pytest.mark.asyncio
async def test_import_keeps_long_lines_as_notes_and_skips_unusable_names(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    long_line = "2 cups flour " + "and a very long story about flour " * 12
    long_tag = "t" * 101
    good_tag = f"Weeknight {random_string(6)}"
    _serve(
        monkeypatch,
        _json_ld_page(
            {
                "name": f"Bread {random_string(6)}",
                "recipeYield": "4 people",
                "recipeIngredient": ["500 g flour", long_line, "salt to taste"],
                "recipeInstructions": [{"@type": "HowToStep", "text": "Knead and bake."}],
                "keywords": f"{good_tag}, !!!, {long_tag}",
            }
        ),
    )
    before = _counts(user)

    result = await import_recipe_from_url(url=_page_url())

    stored = _stored(user, result["slug"])
    flour, story, salt = stored.recipe_ingredient
    assert flour.food is not None and flour.quantity == 500
    assert story.food is None and story.note == long_line.strip() and story.quantity is None
    assert salt.quantity in (None, 0) and salt.original_text == "salt to taste"
    assert stored.recipe_servings == 4  # "4 people"
    assert [t.name.casefold() for t in stored.tags or []] == [good_tag.casefold()]  # the scraper title-cases
    assert _counts(user)["tags"] == before["tags"] + 1


@pytest.mark.asyncio
async def test_import_failed_save_leaves_nothing_behind(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user)
    _serve(
        monkeypatch,
        _json_ld_page(
            {
                "name": "Stew",
                "recipeIngredient": [f"2 {random_string(8)} {random_string(10)}"],
                "recipeInstructions": [{"@type": "HowToStep", "text": "Simmer."}],
                "keywords": random_string(10),
            }
        ),
    )
    before = _counts(user)

    def broken_create_one(self: RecipeService, data: Any) -> Recipe:
        raise RuntimeError("disk full")

    monkeypatch.setattr(RecipeService, "create_one", broken_create_one)

    with pytest.raises(McpToolError, match="^Mealie couldn't save the recipe: disk full. Nothing was saved"):
        await import_recipe_from_url(url=_page_url())

    session.expire_all()
    assert _counts(user) == before


@pytest.mark.asyncio
async def test_import_requires_recipes_write(
    monkeypatch: pytest.MonkeyPatch, session: Session, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    _as_user(monkeypatch, session, user, scopes=["recipes:read"])
    fetched = _serve(monkeypatch, CHICKEN.read_text())

    with pytest.raises(McpToolError, match="recipes:write"):
        await import_recipe_from_url(url=_page_url())
    assert fetched == []


@pytest.mark.asyncio
async def test_import_tool_is_registered():
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}

    schema = tools["import_recipe_from_url"].input_schema
    assert set(schema["properties"]) == {"url", "include_tags"}
    assert schema["required"] == ["url"]
    assert "already_existed" in (tools["import_recipe_from_url"].description or "")
