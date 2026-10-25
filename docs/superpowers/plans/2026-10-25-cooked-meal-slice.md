# Cooked meal slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Marking a meal as cooked (cook mode, Claude, or a tick on the meal plan) marks the plan entry done, moves last made forward, applies the user's pantry choices and adds leftovers, in one all-or-nothing operation.

**Architecture:** One service, `CookedMealService`, owns matching, suggestions and the `record` operation; it runs inside `single_commit(session)` so the auto-committing repositories write all-or-nothing. A household REST controller exposes it to cook mode and the planner; MCP gets `record_meal_cooked` plus `in_pantry` on `get_recipe`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, MCP Python SDK; Nuxt 4 / Vue 3 / Vuetify 4 with the Ds* design system; pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-25-cooked-meal-slice-design.md`

## Global Constraints

- Work in a worktree `.worktrees/feat-cooked-meal` on branch `feat/cooked-meal` (symlink `.venv` to the main checkout's); Python via `uv run --no-sync`; never run two pytest processes at once (`-p no:xdist`).
- Nothing in the pantry changes without an explicit user outcome; no default outcome anywhere.
- Leftover item: name `Leftover {recipe name}`, `source=leftover`, `quantity`=portions, no unit, note `portions`, location `fridge` (or `freezer`), `bought_on`=cooking date, `use_by` = cooking date + 3 days (fridge) / + 90 days (freezer) unless given; portions 1-50.
- Cooking date: the client's local day; refused when later than tomorrow (server's today + 1), as feedback does.
- Entry matching: not-yet-done entry of the user's household, same recipe, dated the cooking date or the day before; closest date wins (then lowest id).
- Already recorded: refuse with `already recorded as cooked on {date}` when an entry with this recipe has `cooked_at` on the cooking date.
- New Household/User relationships, if any, get `info={"filterable": False}` (query-filter leak lesson).
- After schema changes run `task dev:generate`; never hand-edit `frontend/app/lib/api/types/`; only `en-US` locale strings.
- MCP scope for `record_meal_cooked`: `pantry:write`. No reconnect.
- Migrations tested on SQLite and PostgreSQL (throwaway `postgres:17-alpine`, `uv run --no-sync --with psycopg2-binary==2.9.13`).

## Review Focus

1. Editing a done entry through the existing planner (PUT `/households/mealplans/{id}`, drag to another day) keeps `cooked_at` — the update schema doesn't carry it, and the repository must not reset it. Test in Task 1.
2. A failure after some writes (e.g. the leftover insert raises) leaves nothing: no feedback row, no last made change, no removed pantry item, entry not done. Test in Task 2.
3. Pantry ids from another household, or that don't match the recipe, or repeated, are refused before any write. Test in Task 2.
4. A recipe from another household of the group can be recorded as cooked (recipes are group-wide), but the pantry and plan touched are always the user's household. Test in Task 2.
5. The cook-mode Done button is pressed twice quickly / retried after a network error: the second request is refused as already recorded when the first landed, and the UI treats that answer as success. Test in Task 6 (component) and Task 2 (service).

---

### Task 1: `cooked_at` on meal plan entries

**Files:**
- Modify: `mealie/db/models/household/mealplan.py` (`GroupMealPlan`)
- Create: `mealie/alembic/versions/2026-10-25-00.00.02_<rev>_add_meal_plan_cooked_at.py` (down_revision `8e849a1153cf`)
- Modify: `mealie/schema/meal_plan/new_meal.py` (`ReadPlanEntry` only)
- Test: `tests/integration_tests/user_household_tests/test_group_mealplan.py`

**Interfaces:**
- Produces: column `GroupMealPlan.cooked_at: Mapped[datetime | None]` (timezone-aware `NaiveDateTime`/`DateTime` as other timestamp columns in the models use), nullable, no default; `ReadPlanEntry.cooked_at: datetime | None = None`. Not on `CreatePlanEntry`/`UpdatePlanEntry`.

- [ ] **Step 1: Write the failing tests** `test_read_entry_has_cooked_at_none` (create an entry via the API, GET it, `cooked_at` is `None`) and `test_update_keeps_cooked_at` (set `cooked_at` directly through the repo/session, then PUT the entry with a new date and title via the API, GET: `cooked_at` unchanged, date changed).
- [ ] **Step 2: Run** `uv run --no-sync pytest -p no:xdist tests/integration_tests/user_household_tests/test_group_mealplan.py -k cooked -v` — expect FAIL (no attribute).
- [ ] **Step 3: Add the column, migration and schema field.** If the PUT test shows the repository resetting unspecified columns, make the update path leave `cooked_at` alone (exclude it in the controller's update, not by adding it to `UpdatePlanEntry`).
- [ ] **Step 4: Run the tests** — PASS. Run the migration up and down on SQLite and on PostgreSQL.
- [ ] **Step 5: Run** `task dev:generate`; commit `feat(mealplan): cooked_at on plan entries`.

### Task 2: `CookedMealService` and `single_commit`

**Files:**
- Create: `mealie/repos/single_commit.py`
- Create: `mealie/schema/household/cooked_meal.py`
- Create: `mealie/services/claude_context/cooked_meal_service.py`
- Test: `tests/unit_tests/services_tests/test_cooked_meal_service.py`, `tests/unit_tests/repository_tests/test_single_commit.py`

**Interfaces:**
- Consumes: `GroupMealPlan.cooked_at` (Task 1); `PantryService` (add/remove/update item, `sync_on_hand`); `RecipeFeedbackService.record`; `food_name_variants` from `recipe_writer.py`; household profile habits `default_servings`.
- Produces:
  - `single_commit(session: Session) -> ContextManager[None]`: inside, `session.commit` behaves as `session.flush`; on normal exit commits once; on exception rolls back and re-raises; always restores `commit`. Nested use is an error-free no-op for the inner block.
  - Schemas (`mealie/schema/household/cooked_meal.py`, exported via codegen): `PantryOutcome(StrEnum)` = `used_up`, `some_left`; `CookedPantryOutcome{pantry_item_id: UUID4, outcome: PantryOutcome}`; `CookedLeftovers{portions: int (1..50), location: Literal["fridge","freezer"] = "fridge", use_by: date | None = None}`; `CookedFeedback{verdict: FeedbackVerdict, effort: FeedbackEffort | None = None}` (reuse the feedback enums); `CookedMealCreate{recipe_id: UUID4, cooked_on: date, meal_plan_entry_id: int | None = None, scale: float | None (gt 0) = None, pantry: list[CookedPantryOutcome] = [], leftovers: CookedLeftovers | None = None, feedback: CookedFeedback | None = None}`; `CookedMealOut{meal_plan_entry: ReadPlanEntry | None, removed_item_ids: list[UUID4], kept_items: list[PantryItemOut], leftover: PantryItemOut | None, feedback: RecipeFeedbackOut | None}`; `PantryCheckOut{items: list[PantryItemOut], suggested_leftover_portions: int, meal_plan_entry_id: int | None}`.
  - `CookedMealService(repos: AllRepositories, user: PrivateUser, household: HouseholdInDB)` with:
    - `pantry_check(recipe_id: UUID, cooked_on: date, scale: float | None = None) -> PantryCheckOut` — matched items ordered as `get_pantry` orders them; scale = given scale, else the matched entry's `recipe_scale`, else 1.
    - `find_entry(recipe_id: UUID, cooked_on: date) -> ReadPlanEntry | None` — per Global Constraints.
    - `record(data: CookedMealCreate, today: date | None = None) -> CookedMealOut`.
    - `uncook_entry(entry_id: int) -> ReadPlanEntry` — clears `cooked_at` only.
  - Errors: `AlreadyCookedError(ValueError)`, `PantryItemNotInRecipeError(ValueError)` (lists the offending ids), reuse `NoEntryFound` (recipe or entry not visible) and `FutureMadeOnError`.

- [ ] **Step 1: Write the failing tests.**
  - `test_single_commit_commits_once_and_rolls_back`: two repo creates inside, an exception after the second → neither row exists; without the exception both exist.
  - `test_pantry_check_matches_food_and_name_variants`: recipe with "200 g spaghetti" (food spaghetti) and "2 eggs" (food egg) and "salt to taste" (no food); pantry has spaghetti (food linked), "Eggs" (no food), "rice"; result names = {spaghetti, Eggs}.
  - `test_suggested_portions`: recipe servings 4, `default_servings` 2 → 2; scale 2 → 6; no default_servings → 0; servings 2 and default 4 → 0.
  - `test_find_entry_rules`: entries for the recipe yesterday and today → today's; today's done → yesterday's; only 2 days ago → None; another household's entry → None.
  - `test_record_full`: verdict + 1 used_up + 1 some_left (no opened_on) + leftovers 2 fridge, cooked_on today → entry `cooked_at` set, used_up item gone, some_left item `opened_on == cooked_on`, leftover item per Global Constraints (`use_by == cooked_on + 3 days`), one feedback row, recipe last made moved.
  - `test_record_freezer_use_by`: leftovers freezer → `use_by == cooked_on + 90 days`; explicit `use_by` wins.
  - `test_record_refusals_write_nothing`: cooked_on two days ahead; pantry id of another household; pantry id not matching the recipe; repeated pantry id; portions 0 and 51; entry id of another household → each raises, and a snapshot (pantry rows, feedback count, entry `cooked_at`, last made) is unchanged.
  - `test_record_is_all_or_nothing`: monkeypatch the leftover creation to raise → raises; snapshot unchanged (Review Focus 2).
  - `test_record_twice_refused`: record, then record again same recipe and date → `AlreadyCookedError`, still one leftover.
  - `test_record_other_household_recipe`: recipe owned by `h2_user`'s household, recorded by `unique_user` → succeeds; the pantry/entry touched are `unique_user`'s.
  - `test_uncook_entry_keeps_last_made`.
- [ ] **Step 2: Run** `uv run --no-sync pytest -p no:xdist tests/unit_tests/services_tests/test_cooked_meal_service.py tests/unit_tests/repository_tests/test_single_commit.py -v` — FAIL (imports).
- [ ] **Step 3: Implement** `single_commit`, the schemas and the service. `record` order: validate everything (recipe visible group-wide, entry, pantry ids belong to the household and are in `pantry_check`, no repeats, dates, duplicate) → inside `single_commit`: feedback (if any, via `RecipeFeedbackService.record`, which also moves last made) else move last made forward as `RecipeFeedbackService._move_last_made_forward` does (extract it to a shared helper rather than calling a private method) → mark entry → pantry outcomes → leftover.
- [ ] **Step 4: Run the tests** — PASS. Then `task dev:generate`.
- [ ] **Step 5: Commit** `feat(pantry): record a cooked meal (done, pantry outcomes, leftovers)`.

### Task 3: REST endpoints and frontend client

**Files:**
- Create: `mealie/routes/households/controller_cooked_meal.py`; register in `mealie/routes/households/__init__.py`
- Create: `frontend/app/lib/api/user/household-cooking.ts`; register as `householdCooking` in `frontend/app/lib/api/client-user.ts` next to `householdPantry`
- Test: `tests/integration_tests/user_household_tests/test_cooked_meal_routes.py`

**Interfaces:**
- Consumes: Task 2 service and schemas.
- Produces:
  - `GET /api/households/cooking/{recipe_id}/pantry-check?cooked_on=YYYY-MM-DD&scale=` → `PantryCheckOut`
  - `POST /api/households/cooking` body `CookedMealCreate` → `CookedMealOut` (201)
  - `POST /api/households/mealplans/{item_id}/cooked?cooked_on=` → `CookedMealOut` (record with that entry, no pantry, no leftovers; title-only entries just get `cooked_at`, no last made)
  - `DELETE /api/households/mealplans/{item_id}/cooked` → `ReadPlanEntry`
  - Errors: `AlreadyCookedError` → 409; other `ValueError`s → 400; `NoEntryFound` → 404; messages passed through.
  - TS: `HouseholdCookingApi` with `pantryCheck(recipeId, cookedOn, scale?)`, `record(payload: CookedMealCreate)`, `markCooked(entryId, cookedOn)`, `unmarkCooked(entryId)`.

- [ ] **Step 1: Write failing integration tests**: happy path for each endpoint; 409 on a second record; 404 for an entry of another household; 400 for a non-matching pantry id; title-only entry tick sets `cooked_at` and leaves no last made.
- [ ] **Step 2: Run** them — FAIL (404 routes).
- [ ] **Step 3: Implement** the controller (`BaseUserController`, service via property, error mapping in a `_service_errors` context manager like `controller_pantry.py`) and the TS client.
- [ ] **Step 4: Run** the tests — PASS; `task dev:generate`; `pnpm vitest run` and `pnpm nuxi typecheck` in `frontend/` clean.
- [ ] **Step 5: Commit** `feat(pantry): cooked meal endpoints`.

### Task 4: MCP

**Files:**
- Modify: `mealie/mcp/tools/recipes.py` (`get_recipe_impl`), `mealie/mcp/tools/mealplan.py` (`_entries`), `mealie/mcp/tools/pantry.py` (new tool)
- Modify: `docs/fork/deploy.md` (tool list; short "After cooking" section)
- Test: `tests/unit_tests/mcp/test_tools_recipes.py`, `test_tools_mealplan.py`, `test_tools_pantry.py`

**Interfaces:**
- Consumes: `CookedMealService.pantry_check`, `.record`.
- Produces:
  - `get_recipe` adds `in_pantry: [{id, name, quantity, unit, location, opened_on, use_by}]` and `suggested_leftover_portions: int` (from `pantry_check(recipe, today)`).
  - `get_mealplan` / `get_recent_meals` entries add `cooked: bool`.
  - Tool `record_meal_cooked(recipe: str, cooked_on: str | None = None, meal_plan_entry_id: int | None = None, pantry: list[{id: str, outcome: "used_up"|"some_left"}] | None = None, leftover_portions: int | None = None, leftover_location: "fridge"|"freezer" | None = None, leftover_use_by: str | None = None)`, `@require_scope("pantry:write")`; `recipe` is a slug or id; returns `{meal_plan_entry: {id, date, title} | null, removed: [names], kept: [names], leftover: {id, name, portions, location, use_by} | null}`. Docstring: call when the user says a meal was cooked; check `get_recent_meals` first to avoid recording it twice; ask about the `in_pantry` items and leftovers unless the user's own instructions say otherwise; call `record_recipe_feedback` only if the user said how it went; `meal_plan_entry` null means no plan entry was found (not an error).

- [ ] **Step 1: Write failing tests**: `get_recipe` shows a matching pantry item and the suggestion; `get_mealplan` shows `cooked` false then true; `record_meal_cooked` happy path; refused without `pantry:write`; already-recorded error text; bad outcome / bad date refused before writing; tool registered with exactly those parameters.
- [ ] **Step 2: Run** `uv run --no-sync pytest -p no:xdist tests/unit_tests/mcp -v -k "cooked or in_pantry"` — FAIL.
- [ ] **Step 3: Implement**, following `update_pantry`'s argument parsing and error style.
- [ ] **Step 4: Run** the whole `tests/unit_tests/mcp` and `tests/integration_tests/mcp` — PASS. Update the docs.
- [ ] **Step 5: Commit** `feat(mcp): record_meal_cooked; pantry matches in get_recipe`.

### Task 5: Done tick on the meal plan

**Files:**
- Modify: `frontend/app/components/Domain/Planner/PlannerEntryCard.vue` (and its parents only as needed to pass the event/refresh)
- Modify: `frontend/app/lang/messages/en-US.json`
- Test: `frontend/app/components/Domain/Planner/PlannerEntryCard.test.ts` (create if absent)

**Interfaces:**
- Consumes: `HouseholdCookingApi.markCooked/unmarkCooked` (Task 3), `ReadPlanEntry.cookedAt`.
- Produces: a checkbox-style toggle labelled `Cooked` (aria-pressed) on each entry card; a done card shows a check and a muted style; toggling calls the API with today's local date and updates the entry in place; a 409 counts as done.

- [ ] **Step 1: Write failing component tests**: renders not-done and done states; clicking calls `markCooked(entry.id, <today yyyy-MM-dd>)` then shows done; clicking a done entry calls `unmarkCooked`; API error shows the existing error toast and reverts.
- [ ] **Step 2: Run** `pnpm vitest run app/components/Domain/Planner` — FAIL.
- [ ] **Step 3: Implement** with Ds* components and tokens.
- [ ] **Step 4: Run** tests, lint, typecheck — PASS; check it in the browser on the planner.
- [ ] **Step 5: Commit** `feat(planner): mark a meal as cooked`.

### Task 6: Cook mode finish screen

**Files:**
- Modify: `frontend/app/components/Domain/Cook/CookFinish.vue`, `CookMode.vue` (pass `scale`)
- Create: `frontend/app/components/Domain/Cook/CookPantryCheck.vue` (pantry outcomes + leftovers, v-model of the choices)
- Modify: `frontend/app/lang/messages/en-US.json`
- Test: `frontend/app/components/Domain/Cook/CookFinish.test.ts`, `CookPantryCheck.test.ts`

**Interfaces:**
- Consumes: `HouseholdCookingApi.pantryCheck/record` (Task 3).
- Produces: `CookFinish` props add `scale: number`. Verdict buttons select (aria-pressed) instead of saving; effort as today; `CookPantryCheck` lists `pantryCheck` items with *Used up* / *Some left* (none selected; tapping the selected one clears it) and a Leftovers stepper (0-50, pre-filled with `suggestedLeftoverPortions`) with Fridge/Freezer; **Done** sends one `record` with `cookedOn` = local day, `scale`, `mealPlanEntryId` from the check, chosen outcomes, leftovers when > 0, feedback when a verdict was picked, then leaves; **Skip** sends the same without feedback. 409 = success (leave). Other errors: stay, toast `cook.save-failed`, buttons usable for retry. Not logged in: the screen stays as today (no pantry check, no record).

- [ ] **Step 1: Write failing component tests**: no matches and 0 suggestion → no pantry section, Done records with no pantry/leftovers; with matches → outcomes start unselected, choosing *Used up* on one item sends exactly that outcome; leftover stepper pre-filled and sent with location; verdict selected then Done sends feedback; Skip sends no feedback; 409 leaves; 500 stays and retry sends again (Review Focus 5).
- [ ] **Step 2: Run** `pnpm vitest run app/components/Domain/Cook` — FAIL.
- [ ] **Step 3: Implement**, mobile first, Ds* components, cook mode dark tokens.
- [ ] **Step 4: Run** all frontend tests, lint, typecheck — PASS; check it in the browser in cook mode on a recipe with matching pantry items.
- [ ] **Step 5: Commit** `feat(cook): pantry check and leftovers on the finish screen`.
