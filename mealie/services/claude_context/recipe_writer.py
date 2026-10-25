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
from fractions import Fraction
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
from mealie.services.matching import find_match
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


# C0 control characters other than tab, newline and carriage return; PostgreSQL refuses NUL in text
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _printable(text: str) -> str:
    """Refuses control characters and turns Windows (CRLF) and old Mac (CR) line ends into newlines."""
    if _CONTROL_CHARS.search(text):
        raise ValueError("text must not contain control characters (only tab and line breaks are allowed)")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _capped(max_length: int, min_length: int = 1) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


# Strings that must not be blank, with a length cap; surrounding whitespace is dropped.
ShortText = Annotated[str, _capped(MAX_NAME), AfterValidator(_printable)]
Line = Annotated[str, _capped(MAX_LINE), AfterValidator(_printable)]
LongText = Annotated[str, _capped(MAX_TEXT), AfterValidator(_printable)]
Minutes = Annotated[int, Field(ge=0, le=MAX_MINUTES)]


def _matchable(name: str) -> str:
    # foods and units are matched on their normalized name; "!!!" and "???" would both normalize to ""
    if not IngredientFoodModel.normalize(name):
        raise ValueError("a food or unit name needs at least one letter or digit")
    return name


def _sluggable(name: str) -> str:
    # tags, categories and tools are matched and stored by slug; a name with no slug would be dropped silently
    if not slugify(name):
        raise ValueError("a tag, category or tool name needs at least one letter or digit")
    return name


def _recipe_name(name: str) -> str:
    # the recipe's slug (its URL) comes from the name; Mealie refuses a name with no slug
    if not slugify(name):
        raise ValueError("a recipe name needs at least one letter or digit")
    return name


def _web_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise ValueError("source_url must be an http or https link")
    return url


RecipeName = Annotated[str, _capped(MAX_RECIPE_NAME), AfterValidator(_printable), AfterValidator(_recipe_name)]
OrganizerName = Annotated[ShortText, AfterValidator(_sluggable)]
FoodOrUnitName = Annotated[ShortText, AfterValidator(_matchable)]
SourceUrl = Annotated[str, _capped(MAX_URL), AfterValidator(_printable), AfterValidator(_web_url)]
# may be empty (clears the field on an update)
Description = Annotated[str, _capped(MAX_TEXT, min_length=0), AfterValidator(_printable)]
YieldText = Annotated[str, _capped(MAX_NAME, min_length=0), AfterValidator(_printable)]


class _In(BaseModel):
    # allow_inf_nan=False: JSON 1e999 parses to inf, which no quantity or serving count can be
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class IngredientIn(_In):
    """One structured ingredient line. `section` is the section title the line starts."""

    quantity: float | None = Field(default=None, ge=0)
    unit: FoodOrUnitName | None = None
    food: FoodOrUnitName | None = None
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
    description: Description | None = None
    servings: float | None = Field(default=None, gt=0, le=MAX_SERVINGS)
    yield_text: YieldText | None = None
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


class RecipeUpdateIn(RecipeFieldsIn):
    """An update: any recipe field, plus `scale_to_servings` (multiplies the ingredient quantities)."""

    scale_to_servings: float | None = Field(default=None, gt=0, le=MAX_SERVINGS)


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


class _PlannedName(BaseModel):
    name: str


@dataclass
class CreatedRows:
    """Ids of the rows one `apply()` created."""

    foods: list[UUID] = field(default_factory=list)
    units: list[UUID] = field(default_factory=list)
    tags: list[UUID] = field(default_factory=list)
    categories: list[UUID] = field(default_factory=list)
    tools: list[UUID] = field(default_factory=list)


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
        self.created = CreatedRows()

    # --- build ------------------------------------------------------------------------------

    async def build(self, fields: RecipeFieldsIn, base: Recipe | None = None) -> PlannedRecipe:
        """Maps `fields` over `base` (or a blank recipe), parsing and matching without writing."""
        if base is None and fields.name is None:
            raise ValueError("a new recipe needs a name")

        recipe = base.model_copy(deep=True) if base is not None else Recipe(name=fields.name)
        planned = PlannedRecipe(recipe=recipe)
        self._map_scalars(fields, recipe)
        if base is not None:
            self._keep_derived_values(fields, base, recipe)

        if fields.ingredients is not None:
            recipe.recipe_ingredient = [await self._ingredient(item) for item in fields.ingredients]
            self._plan_foods_and_units(planned)

        if fields.instructions is not None:
            recipe.recipe_instructions = [self._step(item) for item in fields.instructions]

        if fields.notes is not None:
            recipe.notes = [RecipeNote(title=note.title, text=note.text) for note in fields.notes]

        resolver = OrganizerResolver(self.repos)
        threshold = resolver.fuzzy_match_threshold
        if fields.tags is not None:
            recipe.tags, planned.new_tags = self._plan_organizers(fields.tags, resolver.resolve_tags, threshold)
        if fields.categories is not None:
            recipe.recipe_category, planned.new_categories = self._plan_organizers(
                fields.categories, resolver.resolve_categories, threshold
            )
        if fields.tools is not None:
            recipe.tools, planned.new_tools = self._plan_organizers(fields.tools, resolver.resolve_tools, threshold)

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
    def _keep_derived_values(fields: RecipeFieldsIn, base: Recipe, recipe: Recipe) -> None:
        """On an update, keeps the values that follow from the ones sent consistent with them.

        - Servings: the yield quantity changes by the same factor, as the UI's scaling does
          ("12 cookies" for 4 servings becomes "6 cookies" for 2).
        - Times: when prep or cook minutes are sent without `total_minutes`, the total is recomputed
          only if it was the sum of its parts (a blank total over blank parts counts). A total that
          includes resting or marinating time ("prep 10, cook 20, total 90"), or free-text times
          from a scraped page, are left alone: they can't be recomputed from the parts.
        """
        if fields.servings is not None:
            _follow_servings(recipe, base.recipe_servings, fields.servings)

        parts_sent = fields.prep_minutes is not None or fields.cook_minutes is not None
        if fields.total_minutes is None and parts_sent and _total_is_sum_of_parts(base):
            total = (recipe.prep_time_seconds or 0) + (recipe.perform_time_seconds or 0)
            recipe.total_time_seconds, recipe.total_time = total or None, None

    @staticmethod
    def scale(recipe: Recipe, servings: float) -> tuple[Recipe, list[str]]:
        """A copy of `recipe` for `servings` servings: every ingredient quantity is multiplied by
        new / old servings, and the yield quantity follows. An ingredient with no quantity (None, or
        0, which the NLP parser stores for "salt to taste") stays as it is; their display texts are
        returned as `not_scaled`.

        The caller makes sure the recipe has servings."""
        old = recipe.recipe_servings
        if not old or old <= 0:
            raise ValueError("the recipe has no servings to scale from")
        scaled = recipe.model_copy(deep=True)
        factor = Fraction(servings) / Fraction(old)
        not_scaled: list[str] = []
        for ingredient in scaled.recipe_ingredient:
            if not ingredient.quantity:
                not_scaled.append(_ingredient_text(ingredient))
                continue
            ingredient.quantity = _scaled_quantity(ingredient.quantity, factor)
        _follow_servings(scaled, old, servings)
        return scaled, not_scaled

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

        if parsed is None or parsed.food is None or not IngredientFoodModel.normalize(parsed.food.name or ""):
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
    def _plan_organizers[T: RecipeTag](
        names: list[str], resolve: Callable[..., list[T]], threshold: int
    ) -> tuple[list[T], list[str]]:
        """Splits names into existing organizers and new names, matched the way `OrganizerResolver`
        matches (slug, then fuzzy at its threshold). A new name that matches a new name planned
        earlier in the same call ("Dinner", "Dinners") is the same organizer, exactly as `apply()`'s
        resolver sees it once the first one exists, so `apply()` creates what is planned here."""
        existing: list[T] = []
        new: list[str] = []
        planned: dict[str, _PlannedName] = {}
        seen: set[UUID | None] = set()
        for name in names:
            matches = resolve([name], create_missing=False)
            if matches:
                if matches[0].id not in seen:
                    seen.add(matches[0].id)
                    existing.append(matches[0])
                continue
            slug = slugify(name)
            if find_match(slug, store_map=planned, fuzzy_match_threshold=threshold) is None:
                planned[slug] = _PlannedName(name=name)
                new.append(name)
        return existing, new

    # --- apply ------------------------------------------------------------------------------

    def apply(self, planned: PlannedRecipe) -> Recipe:
        """Creates what `build()` planned and returns the recipe, ready for `RecipeService`.

        Every row it creates is remembered in `self.created`, so `discard_created()` can remove
        exactly those if the save fails afterwards (the repositories commit on every write)."""
        self.created = CreatedRows()
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
            tags = self._create_organizers(planned.new_tags, resolver.resolve_tags, self.created.tags)
            recipe.tags = self._merge(recipe.tags or [], tags)
        if planned.new_categories:
            categories = self._create_organizers(
                planned.new_categories, resolver.resolve_categories, self.created.categories
            )
            recipe.recipe_category = self._merge(recipe.recipe_category or [], categories)
        if planned.new_tools:
            tools = self._create_organizers(planned.new_tools, resolver.resolve_tools, self.created.tools)
            recipe.tools = self._merge(recipe.tools, tools)

        return recipe

    def _create_food(self, name: str, created: dict[str, IngredientFood]) -> IngredientFood:
        key = IngredientFoodModel.normalize(name)
        if key not in created:
            # matched once more first, so only a food this call really creates is recorded
            food = self.service._get_data_matcher().find_food_match(name)
            if food is None:
                # the importer's helper: creates the food in the user's group
                data = self.service._transform_food({"name": name})
                food = self.repos.ingredient_foods.get_one(data["id"]) if data else None
                if food is None:
                    raise RuntimeError(f"could not create food {name!r}")
                self.created.foods.append(food.id)
            created[key] = food
        return created[key]

    def _create_unit(self, name: str, created: dict[str, IngredientUnit]) -> IngredientUnit:
        key = IngredientUnitModel.normalize(name)
        if key not in created:
            unit = self.service._get_data_matcher().find_unit_match(name)
            if unit is None:
                data = self.service._transform_unit({"name": name})
                unit = self.repos.ingredient_units.get_one(data["id"]) if data else None
                if unit is None:
                    raise RuntimeError(f"could not create unit {name!r}")
                self.created.units.append(unit.id)
            created[key] = unit
        return created[key]

    @staticmethod
    def _create_organizers[T: RecipeTag](
        names: list[str], resolve: Callable[..., list[T]], created: list[UUID]
    ) -> list[T]:
        result: list[T] = []
        for name in names:
            found = resolve([name], create_missing=False)
            if not found:
                found = resolve([name], create_missing=True)
                created.extend(item.id for item in found if item.id is not None)
            result.extend(found)
        return result

    @staticmethod
    def _merge[T: RecipeTag](existing: list[T], added: list[T]) -> list[T]:
        """`existing` plus the items of `added` not already in it; each id once."""
        merged = list(existing)
        ids = {item.id for item in existing}
        for item in added:
            if item.id not in ids:
                ids.add(item.id)
                merged.append(item)
        return merged

    def discard_created(self) -> None:
        """Deletes the rows the last `apply()` created, and only those; used when the save fails.
        Best effort: a row that can't be deleted is logged."""
        repos = self.repos
        for ids, repo in (
            (self.created.tags, repos.tags),
            (self.created.categories, repos.categories),
            (self.created.tools, repos.tools),
            (self.created.foods, repos.ingredient_foods),
            (self.created.units, repos.ingredient_units),
        ):
            for row_id in ids:
                try:
                    repo.delete(row_id)
                except Exception:
                    logger.exception(f"Could not remove {row_id} after a failed recipe save")
        self.created = CreatedRows()

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


def _follow_servings(recipe: Recipe, old: float, new: float) -> None:
    """Sets the servings, and scales the yield quantity by the same factor when both were set."""
    if old and old > 0 and recipe.recipe_yield_quantity:
        recipe.recipe_yield_quantity = round(recipe.recipe_yield_quantity * new / old, 3)
    recipe.recipe_servings = new


def _scaled_quantity(quantity: float, factor: Fraction) -> float:
    """`quantity x factor`, rounded to Mealie's 3 decimals. Quantities are stored rounded (2/3 is
    0.667), so one within that rounding of a kitchen fraction (denominator up to 16) is taken as the
    fraction first: 0.667 x 3/2 gives 1.0, not 1.001."""
    exact = Fraction(quantity)
    kitchen = exact.limit_denominator(16)
    base = kitchen if abs(kitchen - exact) <= Fraction(1, 2000) else exact
    return round(float(base * factor), 3)


def _total_is_sum_of_parts(recipe: Recipe) -> bool:
    if recipe.total_time or recipe.prep_time or recipe.perform_time:
        return False  # free text: nothing to add up
    parts = (recipe.prep_time_seconds or 0) + (recipe.perform_time_seconds or 0)
    return (recipe.total_time_seconds or 0) == parts


def _ingredient_text(ingredient: RecipeIngredient) -> str:
    food = ingredient.food.name if ingredient.food else None
    return ingredient.display or ingredient.original_text or ingredient.note or food or ""


def _start_daemon_thread(task: Callable[[], None]) -> None:
    threading.Thread(target=task, name="mcp-recipe-events", daemon=True).start()


dispatch_off_request: Callable[[Callable[[], None]], None] = _start_daemon_thread
"""Runs the queued event listeners; tests swap it for a synchronous call."""
