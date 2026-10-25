import contextlib
import inspect
from collections.abc import Callable
from typing import Any

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
from mealie.mcp.tools.recipe_write import create_recipe, to_tool_error
from mealie.mcp.tools.recipes import get_recipe_impl
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_category import TagSave
from mealie.schema.recipe.recipe_ingredient import SaveIngredientFood, SaveIngredientUnit
from mealie.schema.response.pagination import PaginationQuery
from mealie.services.claude_context import recipe_writer as recipe_writer_module
from mealie.services.claude_context.recipe_writer import IngredientIn, NoteIn, RecipeCreateIn, RecipeWriter, StepIn
from mealie.services.event_bus_service.event_types import EventTypes
from mealie.services.recipe import recipe_service as recipe_service_module
from mealie.services.recipe.recipe_service import RecipeService
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
    assert set(object_item["properties"]) == {"quantity", "unit", "food", "note", "section"}
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
