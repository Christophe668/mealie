from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mealie.lang.providers import get_locale_provider
from mealie.mcp import context as mcp_context_module
from mealie.mcp.context import McpContext
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_category import TagSave
from mealie.schema.recipe.recipe_ingredient import (
    IngredientFood,
    IngredientUnit,
    SaveIngredientFood,
    SaveIngredientUnit,
)
from mealie.schema.recipe.recipe_tool import RecipeToolSave
from mealie.schema.response.pagination import PaginationQuery
from mealie.schema.user.user import PrivateUser
from mealie.services.claude_context import recipe_writer as recipe_writer_module
from mealie.services.claude_context.recipe_writer import (
    IngredientIn,
    PlannedRecipe,
    RecipeCreateIn,
    RecipeFieldsIn,
    RecipeWriter,
    StepIn,
)
from mealie.services.event_bus_service.event_types import EventTypes
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


def test_publish(monkeypatch: pytest.MonkeyPatch, unique_user: TestUser):
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


def test_publish_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch, unique_user: TestUser):
    class BrokenBus:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dispatch(self, **kwargs: Any) -> None:
            raise RuntimeError("apprise down")

    monkeypatch.setattr(recipe_writer_module, "EventBusService", BrokenBus)
    recipe = Recipe(name="Carbonara", slug="carbonara-y", group_id=unique_user.group_id)

    _writer(unique_user).publish(recipe, "create")  # the recipe is already saved; a notifier must not undo that


def test_mcp_context_household_and_translator(session: Session, unique_user: TestUser):
    user = unique_user.repos.users.get_one(unique_user.user_id)
    assert isinstance(user, PrivateUser)
    ctx = McpContext(user=user, repos=unique_user.repos, session=session, access=None)  # type: ignore[arg-type]

    assert str(ctx.household.id) == unique_user.household_id
    assert ctx.household is ctx.household
    assert ctx.translator.t("recipe.recipe-defaults.step-text")
    assert mcp_context_module.DEFAULT_LOCALE == "en-US"
