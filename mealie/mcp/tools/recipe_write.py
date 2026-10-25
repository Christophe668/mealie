"""Recipe-writing tools (spec § 3). Thin wrappers over `RecipeWriter`, which maps the input to a Mealie
recipe; saving goes through `RecipeService`, as in the UI."""

from collections.abc import Callable
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import ValidationError, WithJsonSchema
from sqlalchemy.exc import SQLAlchemyError

from mealie.core.root_logger import get_logger
from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext
from mealie.mcp.errors import McpToolError
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.mcp.tools._summaries import recipe_url
from mealie.mcp.tools.recipes import get_recipe_impl
from mealie.schema.recipe.recipe import Recipe
from mealie.services.claude_context.recipe_writer import IngredientIn, NoteIn, RecipeCreateIn, RecipeWriter, StepIn

logger = get_logger(__name__)

# Pydantic tags an error inside a union member with the member: a model name ("StepIn") or a
# validator description ("constrained-str", "function-after[_printable(), constrained-str]").
_UNION_MEMBERS = {"str", IngredientIn.__name__, StepIn.__name__, NoteIn.__name__}
# The error a union member reports when the input is the other kind (a string for an object or vice versa).
_WRONG_KIND = {"model_type", "model_attributes_type", "dict_type", "string_type"}


def _is_union_tag(part: str | int) -> bool:
    return isinstance(part, str) and (part in _UNION_MEMBERS or "[" in part or "-" in part)


def to_tool_error(exc: Exception) -> McpToolError:
    """A readable tool error. A `ValidationError` becomes one `field.path: message` per problem,
    joined with "; " (for example `instructions.0.timer_minutes: Input should be greater than or equal
    to 1`); anything else keeps its message."""
    if not isinstance(exc, ValidationError):
        return McpToolError(str(exc))

    messages: list[str] = []
    wrong_kind: dict[str, str] = {}
    paths_with_real_errors: set[str] = set()
    for error in exc.errors():
        loc = list(error["loc"])
        # an unknown key is the last part of its location, whatever it looks like
        key = [loc.pop()] if error["type"] == "extra_forbidden" and loc else []
        parts = [str(part) for part in loc if not _is_union_tag(part)] + [str(k) for k in key]
        in_union = len(parts) < len(error["loc"])
        path = ".".join(parts) or "input"
        message = error["msg"].removeprefix("Value error, ")
        if in_union and error["type"] in _WRONG_KIND:
            # noise unless no member of the union accepted anything
            wrong_kind[path] = "expected a text line or an object"
            continue
        paths_with_real_errors.add(path)
        entry = f"{path}: {message}"
        if entry not in messages:
            messages.append(entry)

    for path, message in wrong_kind.items():
        if not any(p == path or p.startswith(f"{path}.") for p in paths_with_real_errors):
            messages.append(f"{path}: {message}")
    return McpToolError("; ".join(messages) or str(exc))


def _save_error(exc: Exception) -> McpToolError:
    # no SQL in the message: the details are in the log
    reason = "a database error" if isinstance(exc, SQLAlchemyError) else str(exc) or type(exc).__name__
    return McpToolError(f"Mealie couldn't save the recipe: {reason}. Nothing was saved; you can try again.")


async def create_recipe_impl(ctx: McpContext, fields: RecipeCreateIn) -> dict[str, Any]:
    """Validated input → plan (read-only) → create the missing foods, units and organizers → save → event.

    Repositories commit on every write, so refusals happen before `apply()`: `RecipeCreateIn`
    validates, and `build()` parses and matches without writing.

    If `apply()` or the save still fails, what happens depends on whether the recipe row was
    committed (`create_one` commits it before adding the rating and the timeline event):
    - not saved: the rows `apply()` created in this call, and only those, are deleted, and the
      error says nothing was saved;
    - saved: nothing is deleted (the recipe uses those rows) and the call succeeds with a `warning`.
    Once the recipe is saved, a failing read-back or event is also only a `warning`, so Claude
    doesn't retry and create a duplicate."""
    writer = RecipeWriter(ctx.repos, ctx.user, ctx.household, ctx.translator)
    planned = await writer.build(fields)
    # our own id, so a failed save can tell whether the recipe row was committed
    recipe_id = planned.recipe.id = planned.recipe.id or uuid4()

    warnings: list[str] = []
    try:
        created = writer.service.create_one(writer.apply(planned))
    except Exception as e:
        logger.exception("create_recipe: saving the recipe failed")
        ctx.session.rollback()
        saved = ctx.repos.recipes.get_one(recipe_id, "id")
        if saved is None:
            writer.discard_created()
            raise _save_error(e) from e
        created = saved
        warnings.append("the recipe was saved, but one of Mealie's follow-up steps (rating, timeline) failed")

    def add_similar(result: dict[str, Any]) -> None:
        # Mealie saved a duplicate name as "Name (1)"; list the earlier recipes, not the new one
        result["similar_existing"] = writer.similar_existing(fields.name, exclude_id=created.id)

    return finish_saved(ctx, writer, created, "create", warnings, add_similar)


def saved_recipe_fallback(ctx: McpContext, recipe: Recipe, warnings: list[str]) -> dict[str, Any]:
    """The minimal result for a recipe that is saved although a later step failed: enough for Claude
    to point the user at it, and a `warning` that tells it not to write the recipe again."""
    return {
        "id": str(recipe.id),
        "name": recipe.name,
        "slug": recipe.slug,
        "url": recipe_url(ctx.user.group_slug, recipe.slug),
        "warning": "; ".join(warnings) + ". Don't create it again.",
    }


def finish_saved(
    ctx: McpContext,
    writer: RecipeWriter,
    recipe: Recipe,
    operation: Literal["create", "update"],
    warnings: list[str],
    extend: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Everything after a committed save, none of which may fail the call: the `get_recipe` shape for
    the result (plus `extend`'s fields), then the event. A failure is logged and becomes a `warning`
    (with the minimal `saved_recipe_fallback` result when the read-back itself failed)."""
    result: dict[str, Any] | None
    try:
        result = get_recipe_impl(ctx, str(recipe.id))
        if extend is not None:
            extend(result)
    except Exception:
        logger.exception(f"reading back recipe {recipe.slug} failed")
        result = None
        warnings = [*warnings, "the recipe was saved, but reading it back failed; use get_recipe to see it"]
    try:
        writer.publish(recipe, operation)
    except Exception:
        logger.exception(f"publishing the {operation} event for {recipe.slug} failed")
        warnings = [*warnings, "the recipe was saved, but Mealie's notifications for it failed"]

    if result is None:
        return saved_recipe_fallback(ctx, recipe, warnings)
    if warnings:
        result["warning"] = "; ".join(warnings) + ". Don't create it again."
    return result


# The SDK validates arguments against the signature before the tool runs, with an unreadable
# message, so every parameter accepts anything (`Any`) and `RecipeCreateIn` does the validation.
# `WithJsonSchema` still shows Claude the real shape.
_STR = {"type": "string"}
_INGREDIENT = {
    "anyOf": [
        {"type": "string", "description": 'a plain line, e.g. "200 g spaghetti"'},
        {
            "type": "object",
            "properties": {
                "quantity": {"type": "number"},
                "unit": _STR,
                "food": _STR,
                "note": _STR,
                "section": _STR,
            },
        },
    ]
}
_STEP = {
    "anyOf": [
        _STR,
        {
            "type": "object",
            "properties": {"text": _STR, "title": _STR, "timer_minutes": {"type": "integer"}},
            "required": ["text"],
        },
    ]
}
_NOTE = {"type": "object", "properties": {"title": _STR, "text": _STR}, "required": ["title", "text"]}


def _schema(schema: dict[str, Any], optional: bool = True) -> WithJsonSchema:
    return WithJsonSchema({"anyOf": [schema, {"type": "null"}]} if optional else schema)


Str = Annotated[Any, _schema(_STR)]
Number = Annotated[Any, _schema({"type": "number"})]
Integer = Annotated[Any, _schema({"type": "integer"})]
Names = Annotated[Any, _schema({"type": "array", "items": _STR})]


@mcp_server.tool()
@require_scope("recipes:write")
async def create_recipe(
    name: Annotated[Any, _schema(_STR, optional=False)],
    ingredients: Annotated[Any, _schema({"type": "array", "items": _INGREDIENT}, optional=False)],
    instructions: Annotated[Any, _schema({"type": "array", "items": _STEP}, optional=False)],
    description: Str = None,
    servings: Number = None,
    yield_text: Str = None,
    prep_minutes: Integer = None,
    cook_minutes: Integer = None,
    total_minutes: Integer = None,
    tags: Names = None,
    categories: Names = None,
    tools: Names = None,
    notes: Annotated[Any, _schema({"type": "array", "items": _NOTE})] = None,
    source_url: Str = None,
) -> dict[str, Any]:
    """Save a recipe you wrote (or adapted) to Mealie, owned by the user, in their household. When
    cooking for the household, check get_household_context first: respect every member's allergies
    and exclusions. Afterwards add_mealplan_entries can plan the new recipe, for tonight for example.
    ingredients (1-100): prefer structured entries {quantity?, unit?, food?, note?, section?} (food or
    note required) so the shopping list, the pantry and scaling work on them. Structured foods and
    units match existing ones by exact name (ignoring case), and unknown ones are created: reuse the
    food names you saw in get_recipe or search results, and use the singular ("tomato", not
    "tomatoes"). `section` starts a titled group ("Sauce"). A plain line such as "200 g spaghetti"
    is parsed; one with no food ("salt to taste") is kept as a note.
    instructions (1-100): "text" or {text, title?, timer_minutes? (1-1440)}; title is a section title.
    servings 0-100; minutes 0-1440; tags (up to 20), categories, tools: names, matched ignoring case
    or created; notes: [{title, text}]; source_url: the http(s) page you adapted the recipe from.
    Lengths: recipe name 200, food/unit/tag/title 100, ingredient line or note 300, step/note text and
    description 5000 characters. Duplicate names are allowed (Mealie saves "Name (1)").
    Returns the recipe as get_recipe does (with its Mealie `url`), plus `similar_existing`: up to 3
    earlier recipes with the same name, worth mentioning to the user. A `warning` means the recipe was
    saved but something after the save failed: don't create it again."""
    try:
        fields = RecipeCreateIn(
            name=name,
            description=description,
            servings=servings,
            yield_text=yield_text,
            prep_minutes=prep_minutes,
            cook_minutes=cook_minutes,
            total_minutes=total_minutes,
            ingredients=ingredients,
            instructions=instructions,
            tags=tags,
            categories=categories,
            tools=tools,
            notes=notes,
            source_url=source_url,
        )
    except ValidationError as e:
        raise to_tool_error(e) from e
    return await run_in_context(create_recipe_impl, fields)
