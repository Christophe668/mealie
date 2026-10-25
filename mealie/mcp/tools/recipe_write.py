"""Recipe-writing tools (spec § 3). Thin wrappers over `RecipeWriter`, which maps the input to a Mealie
recipe; saving goes through `RecipeService`, as in the UI."""

import re
from typing import Any

from pydantic import ValidationError

from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext
from mealie.mcp.errors import McpToolError
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context
from mealie.mcp.tools.recipes import get_recipe_impl
from mealie.services.claude_context.recipe_writer import RecipeCreateIn, RecipeWriter

# Pydantic tags errors inside a union member with the member ("StepIn", "constrained-str",
# "function-after[...]"). Field names are lower-case identifiers and list indexes are ints.
_UNION_TAG = re.compile(r"^[A-Z]|[\[\-]")
# The error a union member reports when the input is the other kind (a string for an object or vice versa).
_WRONG_KIND = {"model_type", "model_attributes_type", "dict_type", "string_type"}


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
        parts = [str(part) for part in error["loc"] if isinstance(part, int) or not _UNION_TAG.search(part)]
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


async def create_recipe_impl(ctx: McpContext, fields: RecipeCreateIn) -> dict[str, Any]:
    """Validated input → plan (read-only) → create the missing foods, units and organizers → save → event.

    Repositories commit on every write, so a refusal must happen before `apply()`: the input is
    validated by `RecipeCreateIn` and `build()` parses and matches without writing. What runs after
    `apply()` (the save, reads for the response, the event) has nothing left to refuse."""
    writer = RecipeWriter(ctx.repos, ctx.user, ctx.household, ctx.translator)
    planned = await writer.build(fields)

    created = writer.service.create_one(writer.apply(planned))

    result = get_recipe_impl(ctx, str(created.id))
    # Mealie saved a duplicate name as "Name (1)"; list the earlier recipes, not the new one
    result["similar_existing"] = writer.similar_existing(fields.name, exclude_id=created.id)
    writer.publish(created, "create")
    return result


@mcp_server.tool()
@require_scope("recipes:write")
async def create_recipe(
    name: str,
    ingredients: list[dict[str, Any] | str],
    instructions: list[dict[str, Any] | str],
    description: str | None = None,
    servings: float | None = None,
    yield_text: str | None = None,
    prep_minutes: int | None = None,
    cook_minutes: int | None = None,
    total_minutes: int | None = None,
    tags: list[str] | None = None,
    categories: list[str] | None = None,
    tools: list[str] | None = None,
    notes: list[dict[str, Any]] | None = None,
    source_url: str | None = None,
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
    earlier recipes with the same name, worth mentioning to the user."""
    try:
        fields = RecipeCreateIn(
            name=name,
            description=description,
            servings=servings,
            yield_text=yield_text,
            prep_minutes=prep_minutes,
            cook_minutes=cook_minutes,
            total_minutes=total_minutes,
            ingredients=ingredients,  # type: ignore[arg-type]  # validated here
            instructions=instructions,  # type: ignore[arg-type]
            tags=tags,
            categories=categories,
            tools=tools,
            notes=notes,  # type: ignore[arg-type]
            source_url=source_url,
        )
    except ValidationError as e:
        raise to_tool_error(e) from e
    return await run_in_context(create_recipe_impl, fields)
