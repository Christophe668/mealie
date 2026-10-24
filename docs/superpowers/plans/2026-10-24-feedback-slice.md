# Recipe feedback slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record "Loved it / It was fine / Not again" per household, feed it to Claude through MCP, and show it on the recipe page, in cook mode and on Home.

**Architecture:** A household-scoped `recipe_feedback` table behind a `RecipeFeedbackService` that also moves last made forward, sets the cook's rating and writes an upstream timeline event. REST under `/api/households/recipe-feedback`, two MCP tools plus `last_verdict` on existing recipe tools, and three frontend touch points.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic 2; `mcp` SDK 2.3 (patterns in `mealie/mcp/`); Nuxt 4 + Vue 3 with the Ds* primitives; pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-feedback-slice-design.md` (binding), with `2026-10-23-mealie-fork-mcp-design.md` § 4.5 and `2026-10-24-ui-redesign-design.md` § 3.

## Global Constraints

- Scoped by `group_id` + `household_id`; repositories via `AllRepositories`; the pantry slice (`mealie/db/models/household/pantry.py`, `mealie/repos/repository_pantry.py`, `mealie/services/claude_context/pantry_service.py`, `mealie/routes/households/controller_pantry.py`, `mealie/mcp/tools/pantry.py`) is the pattern to copy, including its review fixes (repo `create`/`create_many` always apply the scope; name-like validators only on write schemas; `NoEntryFound` → 404).
- Verdict values exactly `loved`, `ok`, `never_again`; effort 1–3; rating mapping 5 / 3 / 1; last made only moves forward.
- No new MCP scope (`recipes:read` to read, `recipes:write` to record).
- Schemas in `mealie/schema/household/recipe_feedback.py`; run codegen with `PRODUCTION=false TESTING=true uv run --no-sync python dev/code-generation/main.py` and commit only the generated files this slice touches.
- Python via `uv run --no-sync` (shared `.venv`), pytest `-p no:xdist`, never two pytest processes at once; the main checkout's dev servers on :9000/:3000 are the user's.
- UI: tokens only, one saffron element per screen (cook mode: highlighted ingredients; recipe page: Start cooking), sentence case, verbs on buttons, no middle dots, en-US + fr-FR keys.

## Review Focus

- Recording feedback for a recipe in another group must 404 and write nothing (Task 2 `test_record_rejects_foreign_recipe`).
- An old `made_on` must not move last made backwards (Task 2 `test_last_made_only_moves_forward`).
- Deleting a recipe must delete its feedback rows (CASCADE on Postgres; on SQLite the service or repo must not leave orphans that break the summary) (Task 2 `test_summary_ignores_deleted_recipe`).
- `summary` with more than 100 ids must 422, with zero ids must return `{}` (Task 3 tests).
- The pinned Alembic head test moves to the new revision (Task 1).

---

### Task 1: Model, migration, schemas, repository

**Files:**
- Create: `mealie/db/models/household/recipe_feedback.py`, `mealie/alembic/versions/2026-10-24-00.00.01_<rev>_add_recipe_feedback.py`, `mealie/schema/household/recipe_feedback.py`, `mealie/repos/repository_recipe_feedback.py`
- Modify: `mealie/db/models/household/__init__.py`, `mealie/repos/repository_factory.py` (`recipe_feedback` property), `mealie/services/backups_v2/alchemy_exporter.py` (`made_on` in `look_for_date`), the pinned-head test
- Test: `tests/unit_tests/test_recipe_feedback_models.py`

**Interfaces:**
- Produces model `RecipeFeedback` (table `recipe_feedback`, spec § 2 columns), schemas `FeedbackVerdict(StrEnum)`, `RecipeFeedbackCreate` (`recipe_id: UUID4`, `verdict: FeedbackVerdict`, `effort: int | None` (1..3), `note: str | None`, `for_whom: str | None`, `made_on: date | None`), `RecipeFeedbackOut` (+ `id`, `group_id`, `household_id`, `user_id`, `made_on: date`, `timeline_event_id`, `recipe: RecipeSummary`-lite with `id/slug/name`, `user_name: str | None`, `created_at`), `RecipeFeedbackPagination`, `RecipeFeedbackSummary` (`last_verdict`, `last_made_on`, `loved`, `ok`, `never_again`, `total`).
- Produces `RepositoryRecipeFeedback(HouseholdRepositoryGeneric[RecipeFeedbackOut, RecipeFeedback])` with `for_recipe(recipe_id, limit: int | None = None) -> list[RecipeFeedbackOut]`, `latest(limit: int) -> list[RecipeFeedbackOut]`, `summaries(recipe_ids: list[UUID]) -> dict[UUID, RecipeFeedbackSummary]` (one grouped query plus one latest-per-recipe query), and scope-forcing `create`/`create_many`.

- [ ] **Step 1: Tests**: round trip with defaults; `for_recipe` order (made_on desc, created_at desc); `summaries` counts and last verdict across two recipes; household isolation (another household's repo sees nothing); effort outside 1..3 rejected by the schema.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** + migration (FKs with the ondelete rules in § 2, indexes on household_id, recipe_id) + codegen. **Step 4: Run** → PASS; ruff; mypy; alembic up/down/up on a scratch SQLite DB; pinned head moved. **Step 5: Commit** `feat(feedback): recipe feedback model, migration, schemas and repository`.

### Task 2: RecipeFeedbackService

**Files:**
- Create: `mealie/services/claude_context/recipe_feedback_service.py`
- Test: `tests/unit_tests/services_tests/test_recipe_feedback_service.py`

**Interfaces:**
- Produces `RecipeFeedbackService(repos: AllRepositories, user: PrivateUser)` with `record(data: RecipeFeedbackCreate, today: date | None = None) -> RecipeFeedbackOut`, `delete(feedback_id: UUID) -> RecipeFeedbackOut`, `list(recipe_id: UUID | None, page, per_page) -> RecipeFeedbackPagination`, `summaries(recipe_ids: list[UUID]) -> dict[UUID, RecipeFeedbackSummary]`, constants `VERDICT_RATING = {loved: 5, ok: 3, never_again: 1}` and `VERDICT_SUBJECT` (English).
- Uses `HouseholdService.set_household_recipe` for last made (as `RecipeService.update_last_made` does), `repos.user_ratings` (`get_by_user_and_recipe` / `create` / `update`, as `routes/users/ratings.py::set_rating`), `repos.recipe_timeline_events`.

- [ ] **Step 1: Tests**: `test_record_creates_row_rating_timeline_and_last_made`, `test_last_made_only_moves_forward`, `test_rating_mapping` (three verdicts), `test_rating_keeps_favourite`, `test_delete_removes_timeline_event_only`, `test_record_rejects_foreign_recipe`, `test_summary_ignores_deleted_recipe`, `test_made_on_defaults_to_today`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**. **Step 4: Run** → PASS; ruff; mypy. **Step 5: Commit** `feat(feedback): feedback service with rating, last made and timeline`.

### Task 3: REST routes

**Files:**
- Create: `mealie/routes/households/controller_recipe_feedback.py`
- Modify: `mealie/routes/households/__init__.py`
- Test: `tests/integration_tests/user_household_tests/test_recipe_feedback_routes.py`

**Interfaces:** routes exactly as spec § 3; `recipeIds` comma-separated, max 100 → 422 beyond; `NoEntryFound` → 404.

- [ ] **Step 1: Tests**: create 201 + list order; delete; summary for two recipes, zero ids → `{}`, 101 ids → 422; another household's user gets 404 on delete and sees an empty list; unknown recipe → 404.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** + codegen (route helpers). **Step 4: Run** → PASS; the `user_household_tests` folder passes. **Step 5: Commit** `feat(feedback): rest routes for recipe feedback`.

### Task 4: MCP tools and recipe summaries

**Files:**
- Create: `mealie/mcp/tools/feedback.py`
- Modify: `mealie/mcp/tools/__init__.py`, `mealie/mcp/tools/_summaries.py` (`recipe_brief(..., last_verdict: str | None = None)`), `mealie/mcp/tools/recipes.py` (search, recent meals, get_recipe), `mealie/mcp/tools/mealplan.py` if recent meals live there
- Test: `tests/unit_tests/mcp/test_tools_feedback.py`, extend `test_tools_recipes.py`

**Interfaces:** tools per spec § 4; `recipe` accepts slug or id within the user's group; unknown → `not_found("recipe", value)`; invalid verdict/effort/date → `McpToolError` naming the field before any write.

- [ ] **Step 1: Tests**: record via slug and id; scope `recipes:write` required (forbidden with `recipes:read` only); get one recipe's feedback and the latest across recipes; `last_verdict` appears in `search_recipes` and `get_recent_meals`; `get_recipe` has `feedback` (≤ 5) and `feedback_summary`; isolation across households.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (batch summaries once per search call). **Step 4: Run** `tests/unit_tests/mcp tests/integration_tests/mcp` → PASS; ruff; mypy. **Step 5: Commit** `feat(mcp): recipe feedback tools and last verdict in recipe results`.

### Task 5: Frontend — cook finish, recipe page block, Home filter

**Files:**
- Create: `frontend/app/lib/api/user/household-recipe-feedback.ts` (`create`, `list(recipeId)`, `remove(id)`, `summaries(recipeIds)`; registered in `client-user.ts` as `recipeFeedback`), `frontend/app/components/Domain/Recipe/RecipeRead/RecipeReadFeedback.vue`, `RecipeReadFeedbackDialog.vue`
- Modify: `frontend/app/components/Domain/Cook/CookFinish.vue` (effort chips, POST feedback for verdicts, Skip keeps `updateLastMade`, remove sessionStorage parking and its helper), `RecipeReadPage.vue` (mount the block), `frontend/app/composables/use-today.ts` (exclude `never_again` from make-again via `summaries`), locales en-US + fr-FR
- Test: `CookFinish.test.ts` (or extend `CookMode.test.ts`), `RecipeReadFeedback.test.ts`, extend `use-today.test.ts`

- [ ] **Step 1: Tests**: verdict click posts `{ recipeId, verdict, effort? }` and routes back; effort chip toggles; Skip calls `updateLastMade` only; visitor sees Done only; feedback block shows ≤ 3 entries newest first with the relative date line, "for Sam" and note rules, hidden when empty; make-again excludes a `never_again` recipe and keeps the rest when the summary call fails.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**. **Step 4: Run** `pnpm exec vitest run app` → PASS; `pnpm lint`; screenshots (own pair on :9001/:3001) of cook finish at 390 dark and 1280 dark, recipe page with feedback at 390/1280 light and dark, under `.superpowers/sdd/2026-10-24-feedback-slice/screenshots/`. **Step 5: Commit** `feat(ui): recipe feedback in cook mode, recipe page and home`.

### Task 6: Docs, gates, screenshots

- [ ] **Step 1:** `docs/fork/deploy.md` short "Feedback" paragraph; spec "## 7. Implemented" from the ledger; README fork line. **Step 2:** full serial pytest, ruff format --check + check, mypy, `pnpm lint`, vitest, `task ui:build` → all PASS. **Step 3:** screens of cook finish, recipe page with feedback, Home at 390/1280 light/dark under `screens/`. **Step 4: Commit** `docs: recipe feedback slice`.
