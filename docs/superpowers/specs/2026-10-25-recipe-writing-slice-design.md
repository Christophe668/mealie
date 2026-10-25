# Phase 4, slice 1: Claude writes recipes

Date: 2026-10-25. Status: draft for Christophe's approval. Builds on the MCP server from phase 1 (`2026-10-23-mealie-fork-mcp-design.md`) and the tool conventions of the pantry, feedback and profiles slices.

## 1. Why

Christophe wants to tell Claude what he feels like for dinner tonight, and have Claude write the recipe and put it in Mealie with no manual step. Today Claude can read recipes but not write them. (On 2026-10-24 the carbonara had to be added through the REST API by hand.)

Christophe decided:

- **The MCP server only provides the ability.** Whether Claude shows the recipe and asks before saving is up to his own skills and instructions in claude.ai, not up to Mealie.
- **Three abilities:** create a recipe Claude wrote, import a recipe from a web link, and change an existing recipe ("make the carbonara for 4", "remove the cream").
- **Meal planning stays separate.** The skill chains `create_recipe` and the existing `add_mealplan_entries`.

Goals:

- One call creates a complete, usable recipe.
- Its ingredients are structured (quantity, unit, food), so the shopping list, the pantry and scaling work on it.
- Import uses Mealie's existing importer.
- Edits are partial: send only what changes.

Non-goals:

- Deleting recipes.
- Images for Claude-written recipes. An imported recipe keeps the image that the importer downloads.
- Nutrition.
- Bulk import.
- Any UI change.

Anti-goals (a failure even if it technically works):

- A recipe whose ingredients are plain text lines that the shopping list can't merge or scale.
- An edit that silently wipes fields the caller didn't mention.
- Claude editing a recipe the user couldn't edit in Mealie themselves: another household's locked recipe, or one in another group.
- A server-side confirmation rule that forces an extra yes on every write, against Christophe's wish.

## 2. Confirmation policy (server-wide)

The server instructions in `mealie/mcp/server.py` currently say "Always confirm with the user before any write". They become:

> Follow the user's own instructions about confirming changes. When they haven't said, confirm before writing.

Write tools docstrings that say "always confirm before writing" are aligned to the same wording. That covers the meal plan, shopping, pantry, feedback and household tools. Two semantic guards stay, because they are about truth, not confirmation:

- the profile tool's "never infer allergies";
- feedback's rule about not inventing verdicts.

Builder's call: keeping "confirm by default" when the user has said nothing is the safe default. Christophe's skills override it.

## 3. Tools (all scope `recipes:write`, already granted, no reconnect)

### 3.1 `create_recipe`

Parameters:

- `name` (required).
- `description`.
- `servings` (number).
- `yield_text`.
- `prep_minutes`, `cook_minutes`, `total_minutes`.
- `ingredients`: a list. Each item is either:
  - a structured entry `{quantity?, unit?, food?, note?, section?}`, or
  - a plain string such as "200 g spaghetti".
- `instructions`: a list. Each item is either a string or `{text, title?, timer_minutes?}`.
  - `title` is Mealie's section title.
  - `timer_minutes` maps to `duration_seconds`, the field added by the timer work.
- `tags`, `categories`, `tools`: lists of names.
- `notes`: a list of `{title, text}`.
- `source_url`: optional, stored as `org_url` when the recipe adapts one.

Behaviour:

- **Plain-string ingredients** go through Mealie's `nlp` ingredient parser, the UI's default; there is no per-household parser setting. If `nlp` raises, fall back to `brute`. A line the parser can't give a food is kept as a note-only ingredient and never rejected, so "salt to taste" survives. Builder's call.
- **Structured entries** are used as given.
- **Unknown foods and units** are created in the group. Matching is case-insensitive on name, plural and abbreviation, using the same matcher the importer uses (`DataMatcher` and `_transform_food`/`_transform_unit`).
- **Unknown tags and categories** are created. **Tools** are matched or created the same way.
- **Creation goes through `RecipeService.create_one`.** That way household recipe settings, the "created" timeline event, slug uniqueness and permissions all behave as in the UI.
- **Duplicate names are allowed**, because Mealie de-duplicates the slug. The response includes `similar_existing`, up to 3 recipes with the same name, case-insensitive across the group, so Claude can mention them.
- **Validation happens before the write:**
  - name not blank;
  - ingredients list not empty;
  - instructions list not empty;
  - numbers within sane bounds (servings 0 < s ≤ 100; minutes 0–1440; timer 1–1440);
  - list sizes capped: 100 ingredients, 100 steps, 20 tags.

  Errors are readable `McpToolError`s.
- **Returns** the same shape as `get_recipe` for the new recipe, which includes its Mealie `url`, plus `similar_existing`.

### 3.2 `import_recipe_from_url`

Parameters:

- `url` (required, http or https).
- `include_tags` (default true).

Behaviour:

- **Calls Mealie's scraper** (`create_from_html` with the existing fetch safeguards), then saves through `RecipeService.create_one`, the same path as `POST /api/recipes/create/url`. The controller's create-from-web logic moves into a shared service function used by both the REST route and the tool, with regression tests on `/create/url`, rather than being copied. Builder's call.
- **Imported ingredients are parsed and matched** like plain-string ingredients in 3.1, so an import is as usable for shopping and scaling as a Claude-written recipe. The UI leaves them unparsed until you press Parse. Builder's call.
- **If the same URL was already imported into this group**, don't import it again. Return that recipe with `already_existed: true`.
  - Matching rule: scheme and host lower-cased, fragment and trailing slash dropped, query string kept (a different query is a different URL).
  - Stored `org_url` values are normalised the same way in Python before comparing; older rows aren't rewritten.
  - Builder's call.
- **Scraper failures** become readable errors:
  - no recipe found on the page;
  - site unreachable;
  - blocked.
- **Returns** the `get_recipe` shape plus `already_existed`.

### 3.3 `update_recipe`

Parameters:

- `slug_or_id` (required).
- Any of the `create_recipe` fields.
- `scale_to_servings` (number).

Behaviour:

- **Partial update.** Fields that aren't sent stay unchanged.
- **List fields** (`ingredients`, `instructions`, `tags`, `categories`, `tools`, `notes`) replace the whole list when sent. To change one ingredient, Claude sends the full new list, typically after `get_recipe`. Builder's call: this is simpler and more predictable than per-item operations, and recipes are small.
- **`scale_to_servings`** multiplies every ingredient quantity by new/old servings and sets the servings.
  - Ingredients without a quantity, such as "salt to taste", stay as they are and are listed in the response as `not_scaled`.
  - It is refused when the recipe has no servings, and refused when sent together with `ingredients`.
- **Permissions** are the same as the UI: `RecipeService.can_update`. A refusal gives one message: "You can't edit this recipe in Mealie (it is locked, or it belongs to another household that doesn't allow edits)." Recipes in other groups are not found. Builder's call.
- **The update goes through `RecipeService.update_one`** on the merged full recipe, so its checks still run: asset handling, ingredient references and sub-recipes. Step ingredient references to removed ingredients are cleaned the way the UI does it.
- **Validation happens before the write**, with the same rules as create.
- **Returns** the updated recipe in the `get_recipe` shape.

## 4. Shared rules

- **Ownership.** Recipes Claude creates belong to the connected user (`user_id` from the token's user), exactly as if that user had created them in the UI.
- **Events.** Create, import and update publish the same `recipe_created` and `recipe_updated` events (notifications, webhooks) as the REST routes. Builder's call.
- **Group-wide reads, household rules for writes.** `get_recipe` and `search_recipes` already read across the group; `update_recipe` finds a recipe the same way, then checks `can_update`.
- **One code path.** Field mapping (MCP input to Mealie `Recipe`) lives in one helper, `mealie/services/claude_context/recipe_writer.py`, which all three tools use. The tools stay thin, following the existing `*_impl` plus `@mcp_server.tool()` pattern.
- **Docstrings tell Claude:**
  - prefer structured ingredients;
  - check `get_household_context` constraints (allergies, exclusions) before writing a recipe for the household;
  - after creating a recipe for tonight, it can call `add_mealplan_entries`.
- **No schema or database change** is expected. If the builder finds one is needed, it stops and reports.

## 5. Tests

- **Unit, `tests/unit_tests/mcp/test_tools_recipe_write.py`:**
  - create with structured and plain ingredients, with foods and units matched or created;
  - tags, categories and tools created;
  - timers mapped;
  - validation-before-write: a bad call writes nothing, with no stray foods, units or tags;
  - `similar_existing`;
  - update: partial, list replacement, scaling and its refusals;
  - permission and lock refusals;
  - other-group not found;
  - other household's recipe following the household setting;
  - scope `recipes:write` enforced on all three tools.
- **Import:** use the importer's existing test fixtures or recorded HTML; no network in tests. Cover success, already imported, and no recipe found.
- **Server instructions text test**, updated.

## 6. Docs

`docs/fork/deploy.md`:

- add the three tools to the tool list;
- add a short "Claude writes recipes" paragraph, including that the confirmation policy follows the user's own instructions.
