# Recipe writing slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three MCP tools under the existing `recipes:write` scope (`create_recipe`, `update_recipe`, `import_recipe_from_url`) produce complete recipes with structured ingredients. The server-wide confirmation rule becomes "follow the user's own instructions; confirm when they haven't said".

**Architecture:** One mapping and writing service, `mealie/services/claude_context/recipe_writer.py`. It turns MCP input into a Mealie `Recipe`, parses and matches ingredients, and resolves organizers. It writes through `RecipeService` and publishes the same events as the REST routes. The thin tools live in `mealie/mcp/tools/recipe_write.py`. The REST controller's create-from-web code moves into a shared function that both the route and the import tool call.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic 2; `mcp` SDK 2.3; `ingredient-parser-nlp`; pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-recipe-writing-slice-design.md` (binding).

## Global Constraints

- **Scope and permissions:**
  - All three tools use `@require_scope("recipes:write")`.
  - No new scope, no schema change, no migration. If one turns out to be needed, stop and report.
- **Validation before the first write.** Nothing is written, including foods, units, tags, categories and tools, when the call is refused. Limits:
  - name not blank;
  - at least 1 ingredient and at least 1 instruction on create;
  - servings > 0 and ≤ 100;
  - minutes 0–1440;
  - `timer_minutes` 1–1440;
  - at most 100 ingredients, 100 steps and 20 tags.
- **Ingredient parsing:** Plain-string ingredients use `get_parser(RegisteredParser.nlp, …)`, with `brute` as the fallback if `nlp` raises. A line that ends up with no food is stored note-only.
- **Writes go through the same service as the UI:** `RecipeService.create_one` and `update_one`, with `can_update` for permission. The refusal message is exactly: "You can't edit this recipe in Mealie (it is locked, or it belongs to another household that doesn't allow edits)."
- **Events:** create, import and update publish `recipe_created` / `recipe_updated` exactly as the REST routes do.
- **Return shape:** returns reuse `get_recipe_impl`'s shape, from `mealie/mcp/tools/recipes.py`.
- **Commands:**
  - Python via `uv run --no-sync`.
  - pytest `-p no:xdist`, one pytest process at a time.
  - Never use the network in tests; use recorded HTML or monkeypatch the fetch.
  - Don't touch the main checkout's dev servers on :9000/:3000, or the NAS.
- **Branch:** work in `feat/recipe-writing` in the worktree `.worktrees/feat-recipe-writing`, based on `main`.

## Review Focus

- **A plain-string ingredient with an unusual quantity** ("½ cup", "1-2 cloves", "a pinch of salt") is stored without crashing. It becomes either a structured line or a note-only line. Pinned in Task 1, `test_parse_odd_lines`.
- **A refused call leaves no new foods, units or tags behind.** For example, a valid first ingredient with a new food followed by an invalid instruction. Pinned in Task 2, `test_refused_create_writes_nothing`.
- **`update_recipe` on a recipe from another household in the same group** follows that household's setting, and on another group it gives "not found". Pinned in Task 3, `test_update_permissions`.
- **Scaling a recipe whose ingredients have no quantity** leaves those ingredients unchanged and lists them in `not_scaled`. Fractions don't produce float noise: 2/3 × 3/2 gives 1. Pinned in Task 3, `test_scale_to_servings`.
- **Importing the same page twice** with "/" or "#section" differences returns `already_existed: true`, and a different query string imports a new recipe. Pinned in Task 4, `test_import_dedup`.

---

### Task 1: Recipe writer service

**Files:**
- Create: `mealie/services/claude_context/recipe_writer.py`
- Modify: `mealie/mcp/context.py`
- Test: `tests/unit_tests/services_tests/test_recipe_writer.py`

**Interfaces:**
- Produces:
  - Pydantic input models `IngredientIn{quantity: float|None, unit: str|None, food: str|None, note: str|None, section: str|None}`, `StepIn{text: str, title: str|None, timer_minutes: int|None}`, `NoteIn{title: str, text: str}` and `RecipeFieldsIn`.
    - `RecipeFieldsIn` fields are all optional: `name`, `description`, `servings`, `yield_text`, `prep_minutes`, `cook_minutes`, `total_minutes`, `ingredients: list[IngredientIn|str]`, `instructions: list[StepIn|str]`, `tags`, `categories`, `tools`, `notes`, `source_url`.
    - The models enforce the Global limits, with `extra="forbid"`.
  - `RecipeWriter(repos: AllRepositories, user: PrivateUser, household: HouseholdInDB, translator: Translator)` with:
    - `async def build(self, fields: RecipeFieldsIn, base: Recipe | None = None) -> PlannedRecipe`. This is pure: it parses ingredients, resolves names to existing foods, units and organizers, and lists the ones to create. It writes nothing.
    - `def apply(self, planned: PlannedRecipe) -> Recipe`. This creates the missing foods, units, tags, categories and tools, then returns the `Recipe` ready for `RecipeService`.
    - `def similar_existing(self, name: str, exclude_id: UUID | None) -> list[dict]`. Up to 3 matches, `{name, slug, url}`, case-insensitive exact name, group-wide.
    - `def publish(self, recipe: Recipe, operation: Literal["create", "update"]) -> None`. Uses the same event bus call and message keys as `_publish_recipe_created` in `recipe_crud_routes.py`, plus the update equivalent.
  - `McpContext` gains lazily built `household: HouseholdInDB` and `translator: Translator`.
    - Use the same `get_translator` the routes use, with the user's locale or default.
    - The other tools stay unchanged.

- [ ] **Step 1: Write the failing tests**
  - `test_structured_ingredients_match_existing`: food "Spaghetti" matches the existing "spaghetti", unit "g" matches the unit with abbreviation "g", and the plan creates 0 new foods.
  - `test_unknown_food_and_unit_planned_not_written`: after `build`, `repos.ingredient_foods` has no new row. After `apply`, the new food exists in the user's group.
  - `test_parse_plain_lines`: "200 g spaghetti" gives quantity 200, unit g, food spaghetti.
  - `test_parse_odd_lines`: "½ cup milk", "1-2 cloves garlic" and "a pinch of salt" give no exception. Each line is either structured or note-only with the original text kept.
  - `test_nlp_failure_falls_back_to_brute`: monkeypatch the NLP parser to raise, and the line still parses.
  - `test_steps_and_timers`: `StepIn(text, title="Sauce", timer_minutes=10)` gives `RecipeStep.title == "Sauce"` and `duration_seconds == 600`; a plain string step gives `text` only.
  - `test_organizers_resolved_case_insensitively`: an existing tag "Quick" matches "quick", and an unknown category is planned.
  - `test_limits`: 101 ingredients, servings 0, `timer_minutes` 0, and an unknown key each raise `ValidationError`.
  - `test_similar_existing`: case-insensitive and group-wide, at most 3, and `exclude_id` is respected.
- [ ] **Step 2: Run them** with `uv run --no-sync pytest -p no:xdist tests/unit_tests/services_tests/test_recipe_writer.py`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement**
  - Reuse `DataMatcher`, or `RecipeService._transform_food` and `_transform_unit`, for matching. Don't write a new fuzzy matcher.
  - Match organizers with the repos' slug and name lookup.
  - `section` maps to the ingredient's `title`.
- [ ] **Step 4: Run** the tests again. Expected: PASS. Then run `ruff` and `mypy` on the touched files.
- [ ] **Step 5: Commit** with the message `feat(recipes): recipe writer service for Claude-written recipes`.

### Task 2: `create_recipe` tool and the confirmation policy

**Files:**
- Create: `mealie/mcp/tools/recipe_write.py`, registered where the other tool modules are imported.
- Modify: `mealie/mcp/server.py` (`INSTRUCTIONS`), and the write-tool docstrings in `mealie/mcp/tools/{mealplan,shopping,pantry,feedback,household}.py`.
- Test: `tests/unit_tests/mcp/test_tools_recipe_write.py`, plus the existing instructions/context test in `tests/unit_tests/mcp/test_context_and_scopes.py`.

**Interfaces:**
- Consumes: `RecipeWriter` and `RecipeFieldsIn` from Task 1; `get_recipe_impl` from `mealie/mcp/tools/recipes.py`.
- Produces:
  - `create_recipe_impl(ctx: McpContext, fields: RecipeFieldsIn) -> dict`, returning the `get_recipe_impl` shape plus `similar_existing`.
  - The tool `create_recipe(...)`, whose parameters are the spec § 3.1 fields.
  - A helper `to_tool_error(exc) -> McpToolError` in the same module, which formats `ValidationError` as `field: message`. Tasks 3 and 4 reuse it.

- [ ] **Step 1: Write the failing tests**
  - `test_create_minimal`: name, 1 plain ingredient and 1 step give a recipe in the user's household with the user as owner. The returned `url` and `slug` resolve via `get_recipe_impl`.
  - `test_create_full`: structured ingredients with a section, timers, tags, categories, tools, notes, `source_url` stored as `org_url`, and the times.
  - `test_refused_create_writes_nothing`: one valid ingredient with a new food, followed by an empty instruction text. The call raises `McpToolError`. The food count, unit count, tag count and recipe count are all unchanged.
  - `test_create_publishes_event`: monkeypatch the event bus, and `recipe_created` fires once with the slug.
  - `test_create_requires_recipes_write`: a token without the scope is refused.
  - `test_instructions_text`: `INSTRUCTIONS` contains exactly "Follow the user's own instructions about confirming changes. When they haven't said, confirm before writing." and no longer contains "Always confirm".
  - `test_write_docstrings_follow_policy`: no tool docstring in `mealie/mcp/tools/` contains "Always confirm", and `update_household_profile`'s docstring still contains "never infer allergies" (match case-insensitively).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement**
  - Call order: validate (`RecipeFieldsIn`), then `build`, then `apply`, then `RecipeService(...).create_one`, then `publish`. All of it runs in the `run_in_context` session, so a failure after `apply` rolls back with the session.
  - The docstring says:
    - prefer structured ingredients;
    - check `get_household_context` allergies and exclusions first when cooking for the household;
    - `add_mealplan_entries` can plan the new recipe for tonight.
- [ ] **Step 4: Run** the new tests and `tests/unit_tests/mcp`. Expected: PASS. Then run `ruff` and `mypy`.
- [ ] **Step 5: Commit** with the message `feat(mcp): create_recipe tool; confirmation follows the user's instructions`.

### Task 3: `update_recipe` tool

**Files:**
- Modify: `mealie/mcp/tools/recipe_write.py`, `mealie/services/claude_context/recipe_writer.py`
- Test: `tests/unit_tests/mcp/test_tools_recipe_write.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `update_recipe_impl(ctx, slug_or_id: str, fields: RecipeFieldsIn, scale_to_servings: float | None) -> dict`, returning the `get_recipe_impl` shape plus `not_scaled: list[str]` (the display text of the ingredients it left unscaled).
  - The tool `update_recipe(...)`.
  - `RecipeWriter.scale(recipe: Recipe, servings: float) -> tuple[Recipe, list[str]]`.

- [ ] **Step 1: Write the failing tests**
  - `test_update_partial`: sending only `description` leaves the name, ingredients, steps, tags and the image unchanged.
  - `test_update_replaces_lists`: sending `ingredients` with 2 items leaves exactly 2. Step ingredient references to removed ingredients are dropped, without error.
  - `test_scale_to_servings`:
    - 2 → 4 servings doubles the quantities;
    - a note-only "salt to taste" is unchanged and listed in `not_scaled`;
    - 3 servings → 2 servings applied to a quantity of 1.5 gives exactly 1.0.
    - It is refused when the recipe has no servings, and refused together with `ingredients`.
  - `test_update_permissions`:
    - a locked recipe gives the exact Global refusal message;
    - another household's recipe follows that household's `lock_recipe_edits_from_other_households` preference (both settings tested);
    - another group's recipe gives "not found";
    - in each refused case the recipe is unchanged in the DB.
  - `test_update_publishes_event`: `recipe_updated` fires once.
  - `test_refused_update_writes_nothing`: a valid new tag plus an invalid servings value gives no new tag and no change.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement**
  - Look the recipe up group-wide, as `_find_recipe` does, then check `can_update`.
  - Merge the fields over the current recipe: build with `base=current`, then `apply`, then `RecipeService.update_one`, then `publish`.
  - Scale with `round(q * new / old, 3)`, and only where `quantity` is set and non-zero.
- [ ] **Step 4: Run** the tests. Expected: PASS. Then run `ruff` and `mypy`.
- [ ] **Step 5: Commit** with the message `feat(mcp): update_recipe tool with scaling`.

### Task 4: `import_recipe_from_url` and the shared web import

**Files:**
- Create: `mealie/services/recipe/recipe_web_import.py`
- Modify: `mealie/routes/recipe/recipe_crud_routes.py` (`_create_recipe_from_web` and `_finish_recipe_from_web` call the shared function), `mealie/mcp/tools/recipe_write.py`
- Test: `tests/unit_tests/mcp/test_tools_recipe_write.py`, plus the existing `/create/url` route tests, which must pass unchanged.

**Interfaces:**
- Consumes: Tasks 1–2. `RecipeWriter` parses the scraped ingredient strings.
- Produces:
  - `async def import_from_web(repos, service: RecipeService, translator, url: str, html: str | None, include_tags: bool, include_categories: bool, on_progress=None) -> Recipe`. It scrapes, applies tags and categories, and saves. It does not publish; each caller publishes.
  - `normalise_source_url(url: str) -> str`: scheme and host lower-cased, fragment dropped, trailing "/" dropped, query string kept.
  - `import_recipe_from_url_impl(ctx, url: str, include_tags: bool = True) -> dict`, returning the `get_recipe_impl` shape plus `already_existed: bool`.
  - The tool `import_recipe_from_url(...)`.

- [ ] **Step 1: Write the failing tests**
  - `test_import_success`: monkeypatch the scraper fetch to return a recorded schema.org HTML page from `tests/data`, using an existing fixture if there is one. The result is a recipe with a non-empty name, `org_url` set, and ingredients parsed into food and unit where possible. `already_existed` is false and `recipe_created` fires.
  - `test_import_dedup`:
    - the same URL with a trailing "/" or "#x" gives `already_existed: true` and the same id, with no new recipe;
    - "?page=2" gives a new recipe;
    - a pre-existing row whose `org_url` was stored as "HTTPS://Example.com/r/" matches "https://example.com/r".
  - `test_import_errors`:
    - no recipe on the page, unreachable site and an invalid URL scheme each give a readable `McpToolError`;
    - none of these creates a recipe.
  - `test_create_url_route_unchanged`: the existing REST import tests pass; run them as part of this task.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement**
  - Move the scrape and save part of the controller into `import_from_web`.
  - The controller keeps its SSE streaming and its own `_publish_recipe_created`.
  - The tool runs `import_from_web` and then re-parses the ingredients via `RecipeWriter`, before saving if that's practical, otherwise as an immediate update in the same session. Then it publishes.
  - The dedup scan reads only the `id` and `org_url` columns, group-wide where `org_url` is not null.
- [ ] **Step 4: Run** the new tests and `tests/integration_tests/user_recipe_tests` (or wherever the `/create/url` tests live). Expected: PASS. Then run `ruff` and `mypy`.
- [ ] **Step 5: Commit** with the message `feat(mcp): import_recipe_from_url via a shared web import`.

### Task 5: Docs, gates

**Files:**
- Modify: `docs/fork/deploy.md` (add the three tools to the tool list, plus a "Claude writes recipes" paragraph that includes the confirmation policy), `README.md` (one line), and the spec (add "## 7. Implemented").

- [ ] **Step 1: Gates, run one after another**
  - full `uv run --no-sync pytest -p no:xdist tests`;
  - `ruff format --check` and `ruff check`;
  - `uv run --no-sync mypy mealie`.

  Expected: all pass. Record the counts.
- [ ] **Step 2: Docs.** Write the deploy.md paragraph, the README line and spec § 7 (commits, rulings, deferred items).
- [ ] **Step 3: Commit** with the message `docs: recipe writing slice`, then push.
