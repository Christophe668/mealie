"""Turns a recipe written (or edited) by Claude through MCP into a Mealie `Recipe`.

One code path for every recipe-writing tool (spec § 4): input models with the validation limits,
ingredient parsing and matching, organizer resolution, and event publishing. It never saves the
recipe itself; callers save through `RecipeService` so household settings, the timeline event,
slug uniqueness and permissions behave as in the UI.

`build()` is read-only. Only `apply()` creates the missing foods, units, tags, categories and tools,
so a call refused during validation or building leaves nothing behind.
"""

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

import sqlalchemy as sa
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from slugify import slugify
from starlette.background import BackgroundTasks

from mealie.core.config import get_app_settings
from mealie.core.root_logger import get_logger
from mealie.db.models.recipe.ingredient import IngredientFoodModel, IngredientUnitModel
from mealie.db.models.recipe.recipe import RecipeModel
from mealie.lang.providers import Translator
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.recipe.recipe import Recipe, RecipeTag
from mealie.schema.recipe.recipe_ingredient import (
    CreateIngredientFood,
    CreateIngredientUnit,
    IngredientFood,
    IngredientUnit,
    RecipeIngredient,
    RegisteredParser,
)
from mealie.schema.recipe.recipe_notes import RecipeNote
from mealie.schema.recipe.recipe_step import RecipeStep
from mealie.schema.user.user import DEFAULT_INTEGRATION_ID, PrivateUser
from mealie.services.event_bus_service.event_bus_service import EventBusService
from mealie.services.event_bus_service.event_types import EventOperation, EventRecipeData, EventTypes
from mealie.services.parser_services._base import ABCIngredientParser
from mealie.services.parser_services.ingredient_parser import get_parser
from mealie.services.recipe.organizer_resolver import OrganizerResolver
from mealie.services.recipe.recipe_service import RecipeService
from mealie.services.urls import url_constructors as urls

logger = get_logger(__name__)

MAX_INGREDIENTS = 100
MAX_STEPS = 100
MAX_TAGS = 20
# The spec caps tags only; categories, tools and notes get the same cap so no list is unbounded.
MAX_ORGANIZERS = 20
MAX_NOTES = 20
MAX_MINUTES = 1440
MAX_SERVINGS = 100
SIMILAR_LIMIT = 3

MAX_NAME = 100  # food, unit, organizer, step title, ingredient section, note title, yield
MAX_RECIPE_NAME = 200
MAX_LINE = 300  # a plain ingredient line, an ingredient note
MAX_TEXT = 5000  # step text, note text, description
MAX_URL = 2000


# Strings that must not be blank, with a length cap; surrounding whitespace is dropped.
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME)]
RecipeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_RECIPE_NAME)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LINE)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT)]
Minutes = Annotated[int, Field(ge=0, le=MAX_MINUTES)]


def _sluggable(name: str) -> str:
    # tags, categories and tools are matched and stored by slug; a name with no slug would be dropped silently
    if not slugify(name):
        raise ValueError("a tag, category or tool name needs at least one letter or digit")
    return name


def _web_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise ValueError("source_url must be an http or https link")
    return url


OrganizerName = Annotated[ShortText, AfterValidator(_sluggable)]
SourceUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_URL), AfterValidator(_web_url)
]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngredientIn(_In):
    """One structured ingredient line. `section` is the section title the line starts."""

    quantity: float | None = Field(default=None, ge=0)
    unit: ShortText | None = None
    food: ShortText | None = None
    note: Line | None = None
    section: ShortText | None = None

    @model_validator(mode="after")
    def _has_content(self) -> IngredientIn:
        if self.food is None and self.note is None:
            raise ValueError("an ingredient needs a food or a note")
        return self


class StepIn(_In):
    text: LongText
    title: ShortText | None = None
    timer_minutes: int | None = Field(default=None, ge=1, le=MAX_MINUTES)


class NoteIn(_In):
    title: ShortText
    text: LongText


Ingredients = Annotated[list[IngredientIn | Line], Field(min_length=1, max_length=MAX_INGREDIENTS)]
Steps = Annotated[list[StepIn | LongText], Field(min_length=1, max_length=MAX_STEPS)]


class RecipeFieldsIn(_In):
    """Recipe fields as Claude sends them. Every field is optional: on an update, a field left out
    keeps its current value, and a list that is sent replaces the whole list."""

    name: RecipeName | None = None
    description: Annotated[str, StringConstraints(max_length=MAX_TEXT)] | None = None
    servings: float | None = Field(default=None, gt=0, le=MAX_SERVINGS)
    yield_text: Annotated[str, StringConstraints(max_length=MAX_NAME)] | None = None
    prep_minutes: Minutes | None = None
    cook_minutes: Minutes | None = None
    total_minutes: Minutes | None = None
    ingredients: Ingredients | None = None
    instructions: Steps | None = None
    tags: Annotated[list[OrganizerName], Field(max_length=MAX_TAGS)] | None = None
    categories: Annotated[list[OrganizerName], Field(max_length=MAX_ORGANIZERS)] | None = None
    tools: Annotated[list[OrganizerName], Field(max_length=MAX_ORGANIZERS)] | None = None
    notes: Annotated[list[NoteIn], Field(max_length=MAX_NOTES)] | None = None
    source_url: SourceUrl | None = None


class RecipeCreateIn(RecipeFieldsIn):
    """A new recipe: a name, at least one ingredient and at least one instruction are required."""

    name: RecipeName
    ingredients: Ingredients
    instructions: Steps


@dataclass
class PlannedRecipe:
    """The result of `build()`: the recipe as it will be saved, and what `apply()` must create first.

    In `recipe`, ingredients whose food or unit is new hold a `CreateIngredientFood` /
    `CreateIngredientUnit` without an id, and the organizer lists hold only the existing ones.
    The `new_*` lists are display names, de-duplicated.
    """

    recipe: Recipe
    new_foods: list[str] = field(default_factory=list)
    new_units: list[str] = field(default_factory=list)
    new_tags: list[str] = field(default_factory=list)
    new_categories: list[str] = field(default_factory=list)
    new_tools: list[str] = field(default_factory=list)


class RecipeWriter:
    def __init__(self, repos: AllRepositories, user: PrivateUser, household: HouseholdInDB, translator: Translator):
        self.repos = repos
        self.user = user
        self.household = household
        self.translator = translator
        # The service the UI saves through; its exact-match food/unit matcher and its create helpers
        # are the ones the importer uses, so matching here behaves the same.
        self.service = RecipeService(repos, user, household, translator)
        self._nlp: ABCIngredientParser | None = None
        self._brute: ABCIngredientParser | None = None

    # --- build ------------------------------------------------------------------------------

    async def build(self, fields: RecipeFieldsIn, base: Recipe | None = None) -> PlannedRecipe:
        """Maps `fields` over `base` (or a blank recipe), parsing and matching without writing."""
        if base is None and fields.name is None:
            raise ValueError("a new recipe needs a name")

        recipe = base.model_copy(deep=True) if base is not None else Recipe(name=fields.name)
        planned = PlannedRecipe(recipe=recipe)
        self._map_scalars(fields, recipe)

        if fields.ingredients is not None:
            recipe.recipe_ingredient = [await self._ingredient(item) for item in fields.ingredients]
            self._plan_foods_and_units(planned)

        if fields.instructions is not None:
            recipe.recipe_instructions = [self._step(item) for item in fields.instructions]

        if fields.notes is not None:
            recipe.notes = [RecipeNote(title=note.title, text=note.text) for note in fields.notes]

        resolver = OrganizerResolver(self.repos)
        if fields.tags is not None:
            recipe.tags, planned.new_tags = self._plan_organizers(fields.tags, resolver.resolve_tags)
        if fields.categories is not None:
            recipe.recipe_category, planned.new_categories = self._plan_organizers(
                fields.categories, resolver.resolve_categories
            )
        if fields.tools is not None:
            recipe.tools, planned.new_tools = self._plan_organizers(fields.tools, resolver.resolve_tools)

        return planned

    @staticmethod
    def _map_scalars(fields: RecipeFieldsIn, recipe: Recipe) -> None:
        if fields.name is not None:
            recipe.name = fields.name
        if fields.description is not None:
            recipe.description = fields.description
        if fields.servings is not None:
            recipe.recipe_servings = fields.servings
        if fields.yield_text is not None:
            recipe.recipe_yield = fields.yield_text
        if fields.source_url is not None:
            recipe.org_url = fields.source_url
        # Structured times live in the *_seconds columns; the free-text column is cleared, as the scraper does.
        if fields.prep_minutes is not None:
            recipe.prep_time_seconds, recipe.prep_time = fields.prep_minutes * 60, None
        if fields.cook_minutes is not None:
            recipe.perform_time_seconds, recipe.perform_time = fields.cook_minutes * 60, None
        if fields.total_minutes is not None:
            recipe.total_time_seconds, recipe.total_time = fields.total_minutes * 60, None

    @staticmethod
    def _step(item: StepIn | str) -> RecipeStep:
        if isinstance(item, str):
            return RecipeStep(text=item)
        return RecipeStep(
            text=item.text,
            title=item.title or "",
            duration_seconds=item.timer_minutes * 60 if item.timer_minutes else None,
        )

    async def _ingredient(self, item: IngredientIn | str) -> RecipeIngredient:
        if isinstance(item, str):
            return await self._parse_line(item)

        matcher = self.service._get_data_matcher()
        food: IngredientFood | CreateIngredientFood | None = None
        unit: IngredientUnit | CreateIngredientUnit | None = None
        if item.food:
            food = matcher.find_food_match(item.food) or CreateIngredientFood(name=item.food)
        if item.unit:
            unit = matcher.find_unit_match(item.unit) or CreateIngredientUnit(name=item.unit)
        return RecipeIngredient(quantity=item.quantity, unit=unit, food=food, note=item.note, title=item.section)

    async def _parse_line(self, line: str) -> RecipeIngredient:
        """Parses a plain line like the UI's default parser (NLP), with brute force as the fallback.
        A line that ends up without a food is kept as a note-only line, never rejected."""
        parsed: RecipeIngredient | None = None
        try:
            parsed = (await self._parser(RegisteredParser.nlp).parse_one(line)).ingredient
        except Exception:
            logger.exception("NLP ingredient parser failed; falling back to brute force")
            try:
                parsed = (await self._parser(RegisteredParser.brute).parse_one(line)).ingredient
            except Exception:
                logger.exception("Brute force ingredient parser failed; keeping the line as a note")

        if parsed is None or parsed.food is None or not parsed.food.name:
            return RecipeIngredient(quantity=None, note=line, original_text=line)

        return RecipeIngredient(
            quantity=parsed.quantity,
            unit=parsed.unit,
            food=parsed.food,
            note=parsed.note,
            original_text=line,
            substitutions=parsed.substitutions,
        )

    def _parser(self, kind: RegisteredParser) -> ABCIngredientParser:
        if kind == RegisteredParser.nlp:
            if self._nlp is None:
                self._nlp = get_parser(kind, self.user.group_id, self.repos.session, self.translator)
            return self._nlp
        if self._brute is None:
            self._brute = get_parser(kind, self.user.group_id, self.repos.session, self.translator)
        return self._brute

    @staticmethod
    def _plan_foods_and_units(planned: PlannedRecipe) -> None:
        foods: dict[str, str] = {}
        units: dict[str, str] = {}
        for ingredient in planned.recipe.recipe_ingredient:
            if ingredient.food is not None and not isinstance(ingredient.food, IngredientFood):
                foods.setdefault(IngredientFoodModel.normalize(ingredient.food.name), ingredient.food.name)
            if ingredient.unit is not None and not isinstance(ingredient.unit, IngredientUnit):
                units.setdefault(IngredientUnitModel.normalize(ingredient.unit.name), ingredient.unit.name)
        planned.new_foods = list(foods.values())
        planned.new_units = list(units.values())

    @staticmethod
    def _plan_organizers[T: RecipeTag](names: list[str], resolve: Callable[..., list[T]]) -> tuple[list[T], list[str]]:
        """Splits names into existing organizers (matched as the AI importer does) and new names."""
        existing: list[T] = []
        new: list[str] = []
        seen: set[UUID | None] = set()
        for name in names:
            matches = resolve([name], create_missing=False)
            if not matches:
                # the resolver creates one organizer per slug, so "Quick meal" and "quick-meal" are one
                if slugify(name) not in {slugify(n) for n in new}:
                    new.append(name)
            elif matches[0].id not in seen:
                seen.add(matches[0].id)
                existing.append(matches[0])
        return existing, new

    # --- apply ------------------------------------------------------------------------------

    def apply(self, planned: PlannedRecipe) -> Recipe:
        """Creates what `build()` planned and returns the recipe, ready for `RecipeService`."""
        recipe = planned.recipe
        foods: dict[str, IngredientFood] = {}
        units: dict[str, IngredientUnit] = {}

        for ingredient in recipe.recipe_ingredient:
            if ingredient.food is not None and not isinstance(ingredient.food, IngredientFood):
                ingredient.food = self._create_food(ingredient.food.name, foods)
            if ingredient.unit is not None and not isinstance(ingredient.unit, IngredientUnit):
                ingredient.unit = self._create_unit(ingredient.unit.name, units)

        resolver = OrganizerResolver(self.repos)
        if planned.new_tags:
            recipe.tags = self._merge(recipe.tags or [], resolver.resolve_tags(planned.new_tags, create_missing=True))
        if planned.new_categories:
            recipe.recipe_category = self._merge(
                recipe.recipe_category or [], resolver.resolve_categories(planned.new_categories, create_missing=True)
            )
        if planned.new_tools:
            recipe.tools = self._merge(recipe.tools, resolver.resolve_tools(planned.new_tools, create_missing=True))

        return recipe

    def _create_food(self, name: str, created: dict[str, IngredientFood]) -> IngredientFood:
        key = IngredientFoodModel.normalize(name)
        if key not in created:
            # the importer's helper: matches once more, then creates the food in the user's group
            data = self.service._transform_food({"name": name})
            food = self.repos.ingredient_foods.get_one(data["id"]) if data else None
            if food is None:
                raise RuntimeError(f"could not create food {name!r}")
            created[key] = food
        return created[key]

    def _create_unit(self, name: str, created: dict[str, IngredientUnit]) -> IngredientUnit:
        key = IngredientUnitModel.normalize(name)
        if key not in created:
            data = self.service._transform_unit({"name": name})
            unit = self.repos.ingredient_units.get_one(data["id"]) if data else None
            if unit is None:
                raise RuntimeError(f"could not create unit {name!r}")
            created[key] = unit
        return created[key]

    @staticmethod
    def _merge[T: RecipeTag](existing: list[T], added: list[T]) -> list[T]:
        ids = {item.id for item in existing}
        return existing + [item for item in added if item.id not in ids]

    # --- reads and events -------------------------------------------------------------------

    def similar_existing(self, name: str, exclude_id: UUID | None) -> list[dict[str, Any]]:
        """Up to 3 recipes in the user's group (any household) with the same name, ignoring case.

        Mealie saves a duplicate name as "Name (1)", "Name (2)"…, so those count as the same name;
        "Name 2" or "Name (spicy)" are different recipes.
        """
        target = name.strip().casefold()
        numbered = re.compile(rf"{re.escape(target)} \(\d+\)")
        normalized = RecipeModel.normalize(name)
        stmt = (
            # narrows on the indexed normalized name ("Name (1)" normalizes to "name  1"); the exact rule is below
            sa.select(RecipeModel.name, RecipeModel.slug)
            .where(
                RecipeModel.group_id == self.user.group_id,
                sa.or_(
                    RecipeModel.name_normalized == normalized,
                    RecipeModel.name_normalized.startswith(f"{normalized} ", autoescape=True),
                ),
            )
            .order_by(RecipeModel.created_at)
        )
        if exclude_id is not None:
            stmt = stmt.where(RecipeModel.id != exclude_id)

        rows = [
            row
            for row in self.repos.session.execute(stmt)
            if row.name.casefold() == target or numbered.fullmatch(row.name.casefold())
        ]
        base_url = get_app_settings().BASE_URL
        return [
            {"name": row.name, "slug": row.slug, "url": urls.recipe_url(self.user.group_slug, row.slug, base_url)}
            for row in rows[:SIMILAR_LIMIT]
        ]

    def publish(self, recipe: Recipe, operation: Literal["create", "update"]) -> None:
        """Publishes `recipe_created` / `recipe_updated` with the same payload and message as the REST
        routes. Call it after the save (the repositories commit on write).

        The event, URL and message are built here, unguarded, so a coding error surfaces. As in the
        routes, where the event bus hands the listeners to FastAPI's `BackgroundTasks`, the listeners
        (Apprise, webhooks: HTTP calls with a 15 s timeout each) run off the request path: they are
        queued on a `BackgroundTasks` and run by `dispatch_off_request`, on a daemon thread. They open
        their own session. A failing listener is logged, never raised: the recipe is already saved.
        """
        if operation == "create":
            event_type, event_op, message_key = (
                EventTypes.recipe_created,
                EventOperation.create,
                "notifications.generic-created-with-url",
            )
        else:
            event_type, event_op, message_key = (
                EventTypes.recipe_updated,
                EventOperation.update,
                "notifications.generic-updated-with-url",
            )

        url = urls.recipe_url(self.user.group_slug, recipe.slug, get_app_settings().BASE_URL)
        listeners = BackgroundTasks()
        EventBusService(bg=listeners, session=self.repos.session, translator=self.translator).dispatch(
            integration_id=DEFAULT_INTEGRATION_ID,
            group_id=recipe.group_id,
            household_id=recipe.household_id,
            event_type=event_type,
            document_data=EventRecipeData(operation=event_op, recipe_slug=recipe.slug),
            message=self.translator.t(message_key, name=recipe.name, url=url),
        )
        if not listeners.tasks:
            return

        def run_listeners() -> None:
            for task in listeners.tasks:
                try:
                    task.func(*task.args, **task.kwargs)
                except Exception:
                    logger.exception(f"Publishing the {event_type.name} event for {recipe.slug} failed")

        dispatch_off_request(run_listeners)


def _start_daemon_thread(task: Callable[[], None]) -> None:
    threading.Thread(target=task, name="mcp-recipe-events", daemon=True).start()


dispatch_off_request: Callable[[Callable[[], None]], None] = _start_daemon_thread
"""Runs the queued event listeners; tests swap it for a synchronous call."""
