import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mealie.lang.providers import get_locale_provider
from mealie.mcp import context as mcp_context_module
from mealie.mcp.context import McpContext
from mealie.schema.household.group_events import GroupEventNotifierOptions, GroupEventNotifierSave
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_category import CategorySave, TagSave
from mealie.schema.recipe.recipe_ingredient import (
    IngredientFood,
    IngredientUnit,
    SaveIngredientFood,
    SaveIngredientUnit,
)
from mealie.schema.recipe.recipe_tool import RecipeToolSave
from mealie.schema.response.pagination import PaginationQuery
from mealie.schema.user.user import DEFAULT_INTEGRATION_ID, PrivateUser
from mealie.services.claude_context import recipe_writer as recipe_writer_module
from mealie.services.claude_context.recipe_writer import (
    IngredientIn,
    PlannedRecipe,
    RecipeCreateIn,
    RecipeFieldsIn,
    RecipeWriter,
    StepIn,
)
from mealie.services.event_bus_service.event_bus_service import EventBusService
from mealie.services.event_bus_service.event_types import EventTypes
from mealie.services.event_bus_service.publisher import ApprisePublisher
from mealie.services.parser_services.ingredient_parser import NLPParser
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _writer(user: TestUser) -> RecipeWriter:
    private_user = user.repos.users.get_one(user.user_id)
    assert isinstance(private_user, PrivateUser)
    household = user.repos.households.get_one(user.household_id)
    assert isinstance(household, HouseholdInDB)
    return RecipeWriter(user.repos, private_user, household, get_locale_provider("en-US"))


def _count(repo) -> int:
    return len(repo.page_all(PaginationQuery(page=1, per_page=-1)).items)


def _fields(**kwargs: Any) -> RecipeCreateIn:
    data: dict[str, Any] = {"name": random_string(12), "ingredients": ["1 egg"], "instructions": ["Cook."]}
    data.update(kwargs)
    return RecipeCreateIn(**data)


def _ensure_gram(user: TestUser) -> IngredientUnit:
    unit = user.repos.ingredient_units.get_one("gram", "name")
    if unit is None:
        unit = user.repos.ingredient_units.create(
            SaveIngredientUnit(name="gram", abbreviation="g", group_id=user.group_id)
        )
    return unit


def _create_recipe(api_client: TestClient, user: TestUser, name: str) -> tuple[str, UUID]:
    response = api_client.post(api_routes.recipes, json={"name": name}, headers=user.token)
    assert response.status_code == 201, response.text
    slug = response.json()
    body = api_client.get(api_routes.recipes_slug(slug), headers=user.token).json()
    return slug, UUID(body["id"])


@pytest.mark.asyncio
async def test_structured_ingredients_match_existing(unique_user: TestUser):
    food_name = random_string(12)
    abbreviation = random_string(4)
    food = unique_user.repos.ingredient_foods.create(SaveIngredientFood(name=food_name, group_id=unique_user.group_id))
    unit = unique_user.repos.ingredient_units.create(
        SaveIngredientUnit(name=random_string(12), abbreviation=abbreviation, group_id=unique_user.group_id)
    )

    planned = await _writer(unique_user).build(
        _fields(ingredients=[IngredientIn(quantity=200, unit=abbreviation, food=food_name.upper())])
    )

    assert isinstance(planned, PlannedRecipe)
    assert planned.new_foods == []
    assert planned.new_units == []
    ingredient = planned.recipe.recipe_ingredient[0]
    assert isinstance(ingredient.food, IngredientFood) and ingredient.food.id == food.id
    assert isinstance(ingredient.unit, IngredientUnit) and ingredient.unit.id == unit.id
    assert ingredient.quantity == 200


@pytest.mark.asyncio
async def test_unknown_food_and_unit_planned_not_written(unique_user: TestUser):
    food_name = random_string(12)
    unit_name = random_string(12)
    foods_before = _count(unique_user.repos.ingredient_foods)
    units_before = _count(unique_user.repos.ingredient_units)
    writer = _writer(unique_user)

    planned = await writer.build(
        _fields(
            ingredients=[
                IngredientIn(quantity=1, unit=unit_name, food=food_name, section="Sauce"),
                # the same new food twice is planned (and created) once
                IngredientIn(quantity=2, food=food_name.upper()),
            ]
        )
    )

    assert planned.new_foods == [food_name]
    assert planned.new_units == [unit_name]
    assert _count(unique_user.repos.ingredient_foods) == foods_before
    assert _count(unique_user.repos.ingredient_units) == units_before
    assert unique_user.repos.ingredient_foods.get_one(food_name, "name") is None

    recipe = writer.apply(planned)

    created = unique_user.repos.ingredient_foods.get_one(food_name, "name")
    assert created is not None  # the repository is scoped to the user's group
    assert _count(unique_user.repos.ingredient_foods) == foods_before + 1
    assert _count(unique_user.repos.ingredient_units) == units_before + 1
    first, second = recipe.recipe_ingredient
    assert isinstance(first.food, IngredientFood) and first.food.id == created.id
    assert isinstance(second.food, IngredientFood) and second.food.id == created.id
    assert isinstance(first.unit, IngredientUnit) and first.unit.name == unit_name
    assert first.title == "Sauce"


@pytest.mark.asyncio
async def test_parse_plain_lines(unique_user_fn_scoped: TestUser):
    gram = _ensure_gram(unique_user_fn_scoped)

    planned = await _writer(unique_user_fn_scoped).build(_fields(ingredients=["200 g spaghetti"]))

    ingredient = planned.recipe.recipe_ingredient[0]
    assert ingredient.quantity == 200
    assert isinstance(ingredient.unit, IngredientUnit) and ingredient.unit.id == gram.id
    assert ingredient.food is not None and ingredient.food.name.casefold() == "spaghetti"
    assert ingredient.original_text == "200 g spaghetti"
    assert planned.new_foods == ["spaghetti"]


@pytest.mark.asyncio
async def test_parse_odd_lines(unique_user_fn_scoped: TestUser):
    lines = ["½ cup milk", "1-2 cloves garlic", "a pinch of salt", "salt to taste"]

    writer = _writer(unique_user_fn_scoped)
    planned = await writer.build(_fields(ingredients=lines))
    recipe = writer.apply(planned)

    assert len(recipe.recipe_ingredient) == len(lines)
    for line, ingredient in zip(lines, recipe.recipe_ingredient, strict=True):
        assert ingredient.original_text == line
        if ingredient.food is None:
            assert ingredient.note == line
            assert ingredient.unit is None
        else:
            assert isinstance(ingredient.food, IngredientFood)


@pytest.mark.asyncio
async def test_nlp_failure_falls_back_to_brute(monkeypatch: pytest.MonkeyPatch, unique_user_fn_scoped: TestUser):
    _ensure_gram(unique_user_fn_scoped)

    async def boom(self, ingredient_string: str):
        raise RuntimeError("nlp down")

    monkeypatch.setattr(NLPParser, "parse_one", boom)

    planned = await _writer(unique_user_fn_scoped).build(_fields(ingredients=["200 g spaghetti"]))

    ingredient = planned.recipe.recipe_ingredient[0]
    assert ingredient.quantity == 200
    assert ingredient.food is not None and ingredient.food.name.casefold() == "spaghetti"


@pytest.mark.asyncio
async def test_steps_and_timers(unique_user: TestUser):
    planned = await _writer(unique_user).build(
        _fields(instructions=[StepIn(text="Simmer.", title="Sauce", timer_minutes=10), "Serve."])
    )

    first, second = planned.recipe.recipe_instructions or []
    assert first.title == "Sauce"
    assert first.text == "Simmer."
    assert first.duration_seconds == 600
    assert second.text == "Serve."
    assert not second.title
    assert second.duration_seconds is None


@pytest.mark.asyncio
async def test_organizers_resolved_case_insensitively(unique_user: TestUser):
    tag_name = f"Quick{random_string(6)}"
    tag = unique_user.repos.tags.create(TagSave(name=tag_name, group_id=unique_user.group_id))
    tool_name = random_string(10)
    tool = unique_user.repos.tools.create(RecipeToolSave(name=tool_name, group_id=unique_user.group_id))
    new_category = random_string(12)
    new_tool = random_string(12)
    categories_before = _count(unique_user.repos.categories)
    tools_before = _count(unique_user.repos.tools)
    writer = _writer(unique_user)

    planned = await writer.build(
        _fields(tags=[tag_name.lower()], categories=[new_category], tools=[tool_name.upper(), new_tool])
    )

    assert [t.id for t in planned.recipe.tags or []] == [tag.id]
    assert planned.new_tags == []
    assert planned.new_categories == [new_category]
    assert planned.new_tools == [new_tool]
    assert [t.id for t in planned.recipe.tools] == [tool.id]
    assert _count(unique_user.repos.categories) == categories_before
    assert _count(unique_user.repos.tools) == tools_before

    recipe = writer.apply(planned)

    assert [c.name for c in recipe.recipe_category or []] == [new_category]
    assert unique_user.repos.categories.get_one(new_category, "name") is not None
    assert sorted(t.name for t in recipe.tools) == sorted([tool_name, new_tool])
    assert _count(unique_user.repos.tools) == tools_before + 1


@pytest.mark.asyncio
async def test_build_maps_scalar_fields(unique_user: TestUser):
    planned = await _writer(unique_user).build(
        _fields(
            description="Roman classic",
            servings=4,
            yield_text="4 plates",
            prep_minutes=10,
            cook_minutes=15,
            total_minutes=25,
            notes=[{"title": "Tip", "text": "No cream."}],
            source_url="https://example.com/carbonara",
        )
    )

    recipe = planned.recipe
    assert recipe.description == "Roman classic"
    assert recipe.recipe_servings == 4
    assert recipe.recipe_yield == "4 plates"
    assert (recipe.prep_time_seconds, recipe.perform_time_seconds, recipe.total_time_seconds) == (600, 900, 1500)
    assert [(n.title, n.text) for n in recipe.notes or []] == [("Tip", "No cream.")]
    assert recipe.org_url == "https://example.com/carbonara"


@pytest.mark.asyncio
async def test_build_over_base_keeps_unsent_fields(unique_user: TestUser):
    writer = _writer(unique_user)
    base = writer.apply(await writer.build(_fields(description="old", servings=2, tags=[random_string(8)])))

    planned = await writer.build(RecipeFieldsIn(description="new"), base=base)

    assert planned.recipe.description == "new"
    assert planned.recipe.name == base.name
    assert planned.recipe.recipe_servings == 2
    assert [i.reference_id for i in planned.recipe.recipe_ingredient] == [
        i.reference_id for i in base.recipe_ingredient
    ]
    assert [t.name for t in planned.recipe.tags or []] == [t.name for t in base.tags or []]
    assert planned.new_tags == []


def test_limits():
    with pytest.raises(ValidationError):
        RecipeFieldsIn(ingredients=["1 egg"] * 101)
    with pytest.raises(ValidationError):
        RecipeFieldsIn(servings=0)
    with pytest.raises(ValidationError):
        RecipeFieldsIn(servings=101)
    with pytest.raises(ValidationError):
        RecipeFieldsIn(prep_minutes=1441)
    with pytest.raises(ValidationError):
        StepIn(text="Boil.", timer_minutes=0)
    with pytest.raises(ValidationError):
        RecipeFieldsIn(instructions=[{"text": "Boil.", "timer_minutes": 0}])
    with pytest.raises(ValidationError):
        RecipeFieldsIn(colour="red")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        IngredientIn(food="egg", colour="red")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        RecipeFieldsIn(tags=[random_string(6) for _ in range(21)])
    with pytest.raises(ValidationError):
        RecipeFieldsIn(instructions=["Step."] * 101)
    with pytest.raises(ValidationError):
        RecipeFieldsIn(name="   ")
    with pytest.raises(ValidationError):
        RecipeFieldsIn(instructions=[" "])
    with pytest.raises(ValidationError):
        RecipeFieldsIn(ingredients=[IngredientIn()])
    # create needs a name, at least one ingredient and one instruction
    with pytest.raises(ValidationError):
        RecipeCreateIn(name="Soup", ingredients=[], instructions=["Cook."])
    with pytest.raises(ValidationError):
        RecipeCreateIn(name="Soup", ingredients=["1 egg"])  # type: ignore[call-arg]

    assert RecipeFieldsIn(servings=100, prep_minutes=0).servings == 100


def test_similar_existing(api_client: TestClient, unique_user: TestUser, h2_user: TestUser, g2_user: TestUser):
    name = random_string(12)
    mine_slug, mine_id = _create_recipe(api_client, unique_user, name)
    # Mealie renames a duplicate to "NAME (1)" on save; it still counts as the same name
    other_household_slug, _ = _create_recipe(api_client, h2_user, name.upper())
    _create_recipe(api_client, g2_user, name)  # another group: never listed
    _create_recipe(api_client, unique_user, f"{name} soup")
    writer = _writer(unique_user)

    found = writer.similar_existing(name.title(), exclude_id=None)
    assert [f["slug"] for f in found] == [mine_slug, other_household_slug]
    assert all(set(f) == {"name", "slug", "url"} for f in found)
    assert all(f["url"].endswith(f"/r/{f['slug']}") for f in found)

    assert [f["slug"] for f in writer.similar_existing(name, exclude_id=mine_id)] == [other_household_slug]

    for _ in range(3):
        _create_recipe(api_client, unique_user, name)
    assert len(writer.similar_existing(name, exclude_id=None)) == 3


@pytest.fixture
def dispatch_inline(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Runs the off-request event dispatch synchronously; returns the names of the tasks it ran."""
    ran: list[str] = []

    def run_now(task: Callable[[], None]) -> None:
        ran.append(getattr(task, "__name__", "task"))
        task()

    monkeypatch.setattr(recipe_writer_module, "dispatch_off_request", run_now)
    return ran


def test_publish(monkeypatch: pytest.MonkeyPatch, unique_user: TestUser, dispatch_inline: list[str]):
    calls: list[dict[str, Any]] = []

    class FakeBus:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dispatch(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(recipe_writer_module, "EventBusService", FakeBus)
    writer = _writer(unique_user)
    recipe = Recipe(
        name="Carbonara",
        slug="carbonara-x",
        group_id=unique_user.group_id,
        household_id=unique_user.household_id,
        user_id=unique_user.user_id,
    )

    writer.publish(recipe, "create")
    writer.publish(recipe, "update")

    assert [c["event_type"] for c in calls] == [EventTypes.recipe_created, EventTypes.recipe_updated]
    assert all(c["document_data"].recipe_slug == "carbonara-x" for c in calls)
    assert all(str(c["household_id"]) == unique_user.household_id for c in calls)
    assert "carbonara-x" in calls[0]["message"]


def test_publish_does_not_wait_for_listeners(monkeypatch: pytest.MonkeyPatch, unique_user: TestUser):
    """The listeners (Apprise, webhooks) run on another thread, so a slow notifier never holds the tool call."""
    release = threading.Event()
    published = threading.Event()

    def slow_publish(self, event, group_id, household_id) -> None:
        release.wait(5)
        published.set()

    monkeypatch.setattr(EventBusService, "_publish_event", slow_publish)
    recipe = Recipe(
        name="Carbonara", slug="carbonara-s", group_id=unique_user.group_id, household_id=unique_user.household_id
    )

    _writer(unique_user).publish(recipe, "create")  # returns although the listener is still blocked

    assert not published.is_set()
    release.set()
    assert published.wait(5)


def test_publish_listener_failure_is_logged(
    monkeypatch: pytest.MonkeyPatch, unique_user: TestUser, dispatch_inline: list[str], caplog: pytest.LogCaptureFixture
):
    def broken(self, event, group_id, household_id) -> None:
        raise RuntimeError("apprise down")

    monkeypatch.setattr(EventBusService, "_publish_event", broken)
    recipe = Recipe(
        name="Carbonara", slug="carbonara-y", group_id=unique_user.group_id, household_id=unique_user.household_id
    )

    _writer(unique_user).publish(recipe, "create")  # the recipe is already saved; a notifier must not undo that

    assert dispatch_inline
    assert "carbonara-y" in caplog.text


def test_publish_coding_errors_surface(
    monkeypatch: pytest.MonkeyPatch, unique_user: TestUser, dispatch_inline: list[str]
):
    """Building the event (URL, message) is not wrapped: a broken message key must not be hidden in a log."""

    def broken_t(*args: Any, **kwargs: Any) -> str:
        raise KeyError("notifications.missing-key")

    writer = _writer(unique_user)
    writer.translator = SimpleNamespace(t=broken_t)  # type: ignore[assignment]
    recipe = Recipe(
        name="Carbonara", slug="carbonara-z", group_id=unique_user.group_id, household_id=unique_user.household_id
    )

    with pytest.raises(KeyError):
        writer.publish(recipe, "create")
    assert dispatch_inline == []


def test_publish_through_the_real_event_bus(
    monkeypatch: pytest.MonkeyPatch, unique_user_fn_scoped: TestUser, dispatch_inline: list[str]
):
    """The real EventBusService path: an enabled notifier of the user's household receives the event."""
    user = unique_user_fn_scoped
    user.repos.group_event_notifier.create(
        GroupEventNotifierSave(
            name=random_string(8),
            apprise_url="json://localhost:1/hook",
            group_id=user.group_id,
            household_id=user.household_id,
            options=GroupEventNotifierOptions(recipe_created=True),
        )
    )
    received: list[tuple[Any, list[str]]] = []
    monkeypatch.setattr(ApprisePublisher, "publish", lambda self, event, urls: received.append((event, urls)))
    recipe = Recipe(name="Carbonara", slug=random_string(10), group_id=user.group_id, household_id=user.household_id)

    _writer(user).publish(recipe, "create")
    _writer(user).publish(recipe, "update")  # the notifier didn't subscribe to updates

    assert len(received) == 1
    event, urls = received[0]
    assert event.event_type == EventTypes.recipe_created
    assert event.document_data.recipe_slug == recipe.slug
    assert event.integration_id == DEFAULT_INTEGRATION_ID
    assert recipe.slug in event.message.body
    assert urls and urls[0].startswith("json://localhost:1/hook")


def test_mcp_context_household_and_translator(session: Session, unique_user: TestUser):
    user = unique_user.repos.users.get_one(unique_user.user_id)
    assert isinstance(user, PrivateUser)
    ctx = McpContext(user=user, repos=unique_user.repos, session=session, access=None)  # type: ignore[arg-type]

    assert str(ctx.household.id) == unique_user.household_id
    assert ctx.household is ctx.household
    assert ctx.translator.t("recipe.recipe-defaults.step-text")
    assert mcp_context_module.DEFAULT_LOCALE == "en-US"


# --- limits on names and free text ------------------------------------------------------------


@pytest.mark.parametrize("field", ["tags", "categories", "tools"])
@pytest.mark.parametrize("name", ["!!!", "🍝", "🔪 ✨"])
def test_organizer_names_must_slugify(field: str, name: str):
    with pytest.raises(ValidationError, match="letter or digit"):
        RecipeFieldsIn(**{field: [name]})

    assert RecipeFieldsIn(**{field: ["Crème brûlée"]})


def test_text_length_caps():
    def refused(**kwargs: Any) -> None:
        with pytest.raises(ValidationError):
            RecipeFieldsIn(**kwargs)

    refused(name="x" * 201)
    refused(description="x" * 5001)
    refused(yield_text="x" * 101)
    refused(ingredients=["x" * 301])
    refused(ingredients=[{"food": "x" * 101}])
    refused(ingredients=[{"food": "egg", "unit": "x" * 101}])
    refused(ingredients=[{"food": "egg", "note": "x" * 301}])
    refused(ingredients=[{"food": "egg", "section": "x" * 101}])
    refused(instructions=["x" * 5001])
    refused(instructions=[{"text": "x" * 5001}])
    refused(instructions=[{"text": "Boil.", "title": "x" * 101}])
    refused(notes=[{"title": "x" * 101, "text": "ok"}])
    refused(notes=[{"title": "Tip", "text": "x" * 5001}])
    refused(tags=["x" * 101])
    refused(categories=["x" * 101])
    refused(tools=["x" * 101])
    refused(source_url="https://example.com/" + "x" * 2000)
    refused(source_url="ftp://example.com/recipe")
    refused(source_url="javascript:alert(1)")
    refused(source_url="example.com/recipe")

    accepted = RecipeFieldsIn(
        name="x" * 200,
        description="x" * 5000,
        yield_text="x" * 100,
        ingredients=["x" * 300, {"food": "x" * 100, "unit": "x" * 100, "note": "x" * 300, "section": "x" * 100}],
        instructions=["x" * 5000, {"text": "x" * 5000, "title": "x" * 100}],
        notes=[{"title": "x" * 100, "text": "x" * 5000}],
        tags=["x" * 100],
        source_url="HTTP://Example.com/" + "x" * 1981,
    )
    assert accepted.source_url is not None and len(accepted.source_url) == 2000


def test_similar_existing_matches_only_numbered_duplicates(api_client: TestClient, unique_user: TestUser):
    name = f"Pasta {random_string(8)}"
    first_slug, _ = _create_recipe(api_client, unique_user, name)
    renamed_slug, _ = _create_recipe(api_client, unique_user, name)  # Mealie saves it as "NAME (1)"
    _create_recipe(api_client, unique_user, f"{name} 2")  # a different recipe that happens to end in a number
    _create_recipe(api_client, unique_user, f"{name} (spicy)")
    _create_recipe(api_client, unique_user, f"{name} (2b)")

    found = _writer(unique_user).similar_existing(name.lower(), exclude_id=None)

    assert [f["slug"] for f in found] == [first_slug, renamed_slug]
    assert found[1]["name"].endswith("(1)")


# --- build writes nothing; group isolation ----------------------------------------------------


@contextmanager
def _sql_writes(session: Session) -> Iterator[list[str]]:
    """Records every INSERT/UPDATE/DELETE the session's engine runs, plus flushes and commits."""
    writes: list[str] = []
    engine = session.get_bind()

    def on_execute(conn, cursor, statement: str, *args: Any) -> None:
        if statement.lstrip().split(" ", 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    def on_flush(*args: Any) -> None:
        writes.append("flush")

    def on_commit(*args: Any) -> None:
        writes.append("commit")

    sa.event.listen(engine, "before_cursor_execute", on_execute)
    sa.event.listen(session, "after_flush", on_flush)
    sa.event.listen(session, "after_commit", on_commit)
    try:
        yield writes
    finally:
        sa.event.remove(engine, "before_cursor_execute", on_execute)
        sa.event.remove(session, "after_flush", on_flush)
        sa.event.remove(session, "after_commit", on_commit)


@pytest.mark.asyncio
async def test_build_writes_nothing(unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    writer = _writer(user)
    # load the matcher and parsers once, so their first-use reads aren't mistaken for anything else
    await writer.build(_fields())
    session = user.repos.session
    counts = [
        _count(repo)
        for repo in (
            user.repos.ingredient_foods,
            user.repos.ingredient_units,
            user.repos.tags,
            user.repos.categories,
            user.repos.tools,
        )
    ]

    with _sql_writes(session) as writes:
        planned = await writer.build(
            _fields(
                ingredients=[
                    IngredientIn(quantity=1, unit=random_string(10), food=random_string(10)),
                    f"2 tablespoons {random_string(8)}",
                    f"1 cup {random_string(8)}",
                    f"a pinch of {random_string(8)}",
                    f"1.5 kilogram {random_string(8)}",
                    "salt to taste",
                ],
                tags=[random_string(8), random_string(8)],
                categories=[random_string(8)],
                tools=[random_string(8)],
            )
        )
        await writer.build(RecipeFieldsIn(ingredients=["3 cups flour"], tags=[random_string(8)]), base=planned.recipe)

    assert writes == []
    assert not session.new and not session.dirty and not session.deleted
    assert planned.new_foods and planned.new_units
    assert len(planned.new_tags) == 2 and planned.new_categories and planned.new_tools
    assert counts == [
        _count(repo)
        for repo in (
            user.repos.ingredient_foods,
            user.repos.ingredient_units,
            user.repos.tags,
            user.repos.categories,
            user.repos.tools,
        )
    ]


@pytest.mark.asyncio
async def test_other_groups_foods_units_and_organizers_never_match(unique_user: TestUser, g2_user: TestUser):
    food, unit, abbreviation = random_string(10), random_string(10), random_string(4)
    tag, category, tool = random_string(10), random_string(10), random_string(10)
    theirs = {
        "food": g2_user.repos.ingredient_foods.create(SaveIngredientFood(name=food, group_id=g2_user.group_id)),
        "unit": g2_user.repos.ingredient_units.create(
            SaveIngredientUnit(name=unit, abbreviation=abbreviation, group_id=g2_user.group_id)
        ),
        "tag": g2_user.repos.tags.create(TagSave(name=tag, group_id=g2_user.group_id)),
        "category": g2_user.repos.categories.create(CategorySave(name=category, group_id=g2_user.group_id)),
        "tool": g2_user.repos.tools.create(RecipeToolSave(name=tool, group_id=g2_user.group_id)),
    }
    their_ids = {item.id for item in theirs.values()}
    writer = _writer(unique_user)

    planned = await writer.build(
        _fields(
            ingredients=[
                IngredientIn(quantity=1, unit=unit, food=food),
                IngredientIn(quantity=2, unit=abbreviation, food=food.upper()),
            ],
            tags=[tag],
            categories=[category],
            tools=[tool],
        )
    )

    assert planned.new_foods == [food]
    assert sorted(planned.new_units) == sorted([unit, abbreviation])
    assert (planned.new_tags, planned.new_categories, planned.new_tools) == ([tag], [category], [tool])

    recipe = writer.apply(planned)

    created = [
        *(i.food for i in recipe.recipe_ingredient),
        *(i.unit for i in recipe.recipe_ingredient),
        *(recipe.tags or []),
        *(recipe.recipe_category or []),
        *recipe.tools,
    ]
    assert all(item is not None and item.id not in their_ids for item in created)
    mine = unique_user.repos
    for item, repo in [
        (recipe.recipe_ingredient[0].food, mine.ingredient_foods),
        (recipe.recipe_ingredient[0].unit, mine.ingredient_units),
        ((recipe.tags or [])[0], mine.tags),
        ((recipe.recipe_category or [])[0], mine.categories),
        (recipe.tools[0], mine.tools),
    ]:
        assert item is not None
        assert repo.get_one(item.id) is not None  # the user's repositories are scoped to their group
    # their rows are untouched and still theirs
    assert g2_user.repos.ingredient_foods.get_one(theirs["food"].id) is not None
    assert g2_user.repos.tags.get_one(tag, "name") is not None
    assert mine.ingredient_foods.get_one(theirs["food"].id) is None


# ---------------------------------------------------------------------- scraped recipes (import)


@pytest.mark.parametrize(
    ("servings", "quantity", "text", "expected"),
    [
        (0, 6, "", (6, 0, "")),  # a bare "6": schema.org's servings
        (0, 4, "people", (4, 0, "")),
        (0, 4, "Persons.", (4, 0, "")),
        (0, 12, "cookies", (0, 12, "cookies")),  # a real yield
        (0, 4, "to 6", (0, 4, "to 6")),  # ambiguous: left alone
        (0, 1, "9-inch pie", (0, 1, "9-inch pie")),
        (4, 4, "", (4, 4, "")),  # already has servings
        (0, 0, "", (0, 0, "")),
    ],
)
def test_servings_from_yield(servings: float, quantity: float, text: str, expected: tuple[float, float, str]):
    recipe = Recipe(name="r", recipe_servings=servings, recipe_yield_quantity=quantity, recipe_yield=text)

    recipe_writer_module.servings_from_yield(recipe)

    assert (recipe.recipe_servings, recipe.recipe_yield_quantity, recipe.recipe_yield or "") == expected


def test_usable_organizer_names():
    names = ["Dinner", "  Quick  ", "!!!", "", "x" * 101, "y" * 100, "a\x00b"]

    assert recipe_writer_module.usable_organizer_names(names) == ["Dinner", "Quick", "y" * 100, "ab"]
