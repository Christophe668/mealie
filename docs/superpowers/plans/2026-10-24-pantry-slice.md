# Pantry slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A household pantry with bought/opened/use-by dates, "Put away" from the shopping list, and MCP tools so Claude can read and maintain it.

**Architecture:** A new household-scoped `pantry_items` table behind a `PantryService` that owns the merge rule and keeps Mealie's existing "on hand" foods in sync (so upstream's shopping deduction works unchanged). REST routes under `/api/households`, three MCP tools in `mealie/mcp/tools/pantry.py`, a Pantry page and a "Put away" button on the redesigned frontend.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + Pydantic 2; `mcp` SDK 2.3 (phase 1 patterns in `mealie/mcp/`); Nuxt 4 + Vue 3 with the Ds* primitives; pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-pantry-slice-design.md` (binding), with `docs/superpowers/specs/2026-10-23-mealie-fork-mcp-design.md` § 4.5 and `docs/superpowers/specs/2026-10-24-ui-redesign-design.md` § 3.

## Global Constraints

- Everything scoped by `group_id` + `household_id` (spec § 3); repositories from `AllRepositories`, never raw session access in routes or tools.
- Schemas in `mealie/schema/household/pantry.py`; after any schema change run `task dev:generate` and commit the generated TypeScript (`frontend/app/lib/api/types/household.ts`) and schema `__init__.py` exports; never hand-edit generated files.
- Location enum values exactly `fridge`, `freezer`, `cupboard`, `other`; source enum `shopping`, `manual`, `leftover`; new MCP scope string `pantry:write`.
- Default pantry order: `use_by` ascending with nulls last, then `bought_on` descending.
- Merge rule and on-hand sync exactly as spec § 3.
- UI: tokens only (`--ds-*`), Ds* primitives, one saffron element per screen, sentence case, verbs on buttons, no middle dots, en-US + fr-FR keys (fork ruling), `--ds-tabbar-clearance` for pinned elements.
- Python: `uv run`, ruff format/check, mypy clean on new files; tests `-p no:xdist` when run from a worktree sharing the dev DB with another checkout.

## Review Focus

- Put-away on a list that belongs to another household must 404, never move items (Task 2 test `test_put_away_rejects_foreign_list`).
- A pantry item whose food was deleted upstream must still list (food_id null-safe) (Task 2 test `test_list_survives_deleted_food`).
- Removing one of two pantry rows for the same food must keep the food on hand (Task 2 test `test_on_hand_kept_while_another_row_exists`).
- `update_pantry` with an id from another household must raise not_found and change nothing (Task 4 test `test_update_pantry_isolated_by_household`).
- The pinned Alembic head in `tests/integration_tests/user_recipe_tests/test_recipe_step_duration_migration.py` must move to the new revision or the suite fails (Task 1 step 6).

---

### Task 1: Model, migration, schemas, repository

**Files:**
- Create: `mealie/db/models/household/pantry.py`, `mealie/alembic/versions/2026-10-24-00.00.00_<rev>_add_pantry_items.py` (generate with `task py:migrate -- "add pantry items"`), `mealie/schema/household/pantry.py`, `mealie/repos/repository_pantry.py`
- Modify: `mealie/db/models/household/__init__.py` (export), `mealie/db/models/_all_models.py` if it lists modules, `mealie/repos/repository_factory.py` (add `pantry_items` cached_property after `group_meal_plan_rules`), `mealie/services/backups_v2/alchemy_exporter.py` only if a new datetime column name is not in `look_for_date` (`bought_on`, `opened_on`, `use_by` → add to `look_for_date`), `tests/integration_tests/user_recipe_tests/test_recipe_step_duration_migration.py` (pinned head → new revision)
- Test: `tests/unit_tests/test_pantry_models.py`

**Interfaces:**
- Produces model `PantryItem(SqlAlchemyBase, BaseMixins)` table `pantry_items` with the spec § 3 columns; relationships `food: IngredientFood | None`, `unit: IngredientUnit | None`.
- Produces schemas: `PantryLocation(StrEnum)`, `PantrySource(StrEnum)`, `PantryItemCreate(MealieModel)` (`name: str`, `food_id: UUID4 | None = None`, `quantity: float | None = None`, `unit_id: UUID4 | None = None`, `location: PantryLocation = cupboard`, `bought_on: date | None = None`, `opened_on: date | None = None`, `use_by: date | None = None`, `source: PantrySource = manual`, `note: str | None = None`), `PantryItemUpdate(PantryItemCreate)`, `PantryItemOut(PantryItemCreate)` (+ `id: UUID4`, `group_id`, `household_id`, `food: IngredientFood | None`, `unit: IngredientUnit | None`, `created_at`, `updated_at`), `PantryItemPagination(PaginationBase)` (`items: list[PantryItemOut]`), `PutAwayRequest(MealieModel)` (`item_ids: list[UUID4] | None = None`), `PutAwayResult(MealieModel)` (`created: list[PantryItemOut]`, `merged: list[PantryItemOut]`, `removed_item_ids: list[UUID4]`).
- Produces `RepositoryPantryItems(HouseholdRepositoryGeneric[PantryItemOut, PantryItem])` with `by_food(food_id: UUID) -> list[PantryItemOut]`, `by_name(name: str) -> list[PantryItemOut]` (case-folded equality, `food_id IS NULL`), `ordered(location: PantryLocation | None = None) -> list[PantryItemOut]` (spec default order). Available as `repos.pantry_items`.

- [ ] **Step 1: Write the failing tests** in `tests/unit_tests/test_pantry_models.py`: `test_pantry_item_round_trip` (create via `unique_user.repos.pantry_items.create(PantryItemCreate(name="Eggs", bought_on=date(2026, 10, 24)))`, read back, `household_id == unique_user.household_id`, `location == PantryLocation.cupboard`), `test_ordered_puts_use_by_first_and_nulls_last` (three rows: use_by 2026-10-26, none with bought_on 2026-10-24, use_by 2026-10-25 → names in order [25th, 26th, none]), `test_by_name_is_case_insensitive` ("Crème fraîche" found by "crème FRAÎCHE").
- [ ] **Step 2: Run** `uv run pytest tests/unit_tests/test_pantry_models.py -p no:xdist -q` → FAIL (import error).
- [ ] **Step 3: Implement** the model (pattern: `GroupMealPlanRules` in `mealie/db/models/household/mealplan.py`, with `household_id` nullable=False here), generate and tidy the migration (indexes on `household_id`, `food_id`; downgrade drops the table), the schemas, the repository (`ordered` uses `nulls_last(PantryItem.use_by.asc())` then `PantryItem.bought_on.desc()`), the factory property, `look_for_date` additions.
- [ ] **Step 4: Run** `task dev:generate` and check `frontend/app/lib/api/types/household.ts` now contains `PantryItemOut`.
- [ ] **Step 5: Run** the test file → PASS; `uv run ruff format && uv run ruff check`; `task py:mypy` → clean.
- [ ] **Step 6: Update the pinned head** in `test_recipe_step_duration_migration.py` to the new revision; run that test → PASS.
- [ ] **Step 7: Commit** `feat(pantry): pantry item model, migration, schemas and repository`.

### Task 2: PantryService (merge rule, on-hand sync, put away)

**Files:**
- Create: `mealie/services/claude_context/__init__.py`, `mealie/services/claude_context/pantry_service.py`
- Test: `tests/unit_tests/services_tests/test_pantry_service.py`

**Interfaces:**
- Consumes Task 1 schemas and `repos.pantry_items`, `repos.group_shopping_list_item`, `repos.group_shopping_lists`, `repos.ingredient_foods`, `repos.households`.
- Produces `class PantryService(BaseService)` with `__init__(self, repos: AllRepositories)` and:
  - `list_items(self, location: PantryLocation | None = None) -> list[PantryItemOut]`
  - `add_item(self, data: PantryItemCreate) -> tuple[PantryItemOut, bool]` (bool = merged)
  - `update_item(self, item_id: UUID, data: PantryItemUpdate) -> PantryItemOut` (raises `NotFound`-style `HTTPException(404)` via the repo's behaviour when missing)
  - `remove_item(self, item_id: UUID) -> PantryItemOut`
  - `put_away(self, list_id: UUID, item_ids: list[UUID] | None, today: date | None = None) -> PutAwayResult`
  - `sync_on_hand(self, food_id: UUID) -> None` (spec § 3 rule; uses the household's `ingredient_foods_on_hand` relationship through `repos.households`/the session, the same table upstream's `ShoppingListService._is_on_hand` reads).

- [ ] **Step 1: Write the failing tests**: `test_add_merges_same_food` (two adds with the same food_id → one row, merged flag True, `bought_on` = second date, `opened_on` kept from the first), `test_add_merges_same_name_without_food` ("eggs" / "Eggs"), `test_merge_adds_quantities_only_with_same_unit` (2 + 3 same unit → 5; different unit → quantity 2 and note contains "3"), `test_add_marks_food_on_hand` (after add, `ShoppingListService(repos)._is_on_hand(list_id, food)` is True), `test_on_hand_kept_while_another_row_exists`, `test_remove_last_row_clears_on_hand`, `test_put_away_moves_checked_items` (list with 2 checked + 1 unchecked; result has 2 created, removed_item_ids = the 2; the list keeps 1 item; pantry rows have `source == shopping`, `bought_on == today`, food_id/unit_id/quantity copied, name = food name or item note), `test_put_away_rejects_unchecked_ids` (422), `test_put_away_rejects_foreign_list` (list of another household → 404), `test_list_survives_deleted_food`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `PantryService`. Name for a put-away item: `item.food.name` if food else `item.note or item.display`. Deletion of shopping items through `repos.group_shopping_list_item.delete`. Commit once per public method.
- [ ] **Step 4: Run** tests → PASS; ruff; mypy.
- [ ] **Step 5: Commit** `feat(pantry): pantry service with merge rule, on-hand sync and put away`.

### Task 3: REST routes

**Files:**
- Create: `mealie/routes/households/controller_pantry.py`
- Modify: `mealie/routes/households/__init__.py` (include `controller_pantry.router` and `controller_pantry.put_away_router` before `controller_shopping_lists.router`)
- Test: `tests/integration_tests/household_tests/test_pantry_routes.py`; run `task dev:generate` so `tests/utils/api_routes/__init__.py` gains the routes.

**Interfaces:**
- Consumes `PantryService` (Task 2).
- Produces routes exactly as spec § 4: `GET/POST /api/households/pantry`, `GET/PUT/DELETE /api/households/pantry/{item_id}`, `POST /api/households/shopping/lists/{list_id}/put-away`. Controller `HouseholdPantryController(BaseUserController)` with `@router.get("", response_model=PantryItemPagination)` using `PaginationQuery` like `controller_mealplan_rules.py` but ordered via `PantryService.list_items` when no `order_by` is given.

- [ ] **Step 1: Write the failing tests**: `test_create_and_list` (201 then list contains it, default order check with two items), `test_create_merge_returns_200`, `test_update_and_delete`, `test_put_away_route` (seed a list with checked items via `api_routes.households_shopping_lists*`, POST put-away with `{"item_ids": null}` → 200, `created` length, list items gone), `test_pantry_isolated_between_households` (second household's user gets 404 on the first's item id).
- [ ] **Step 2: Run** → FAIL (404 on unknown route).
- [ ] **Step 3: Implement** the controller; put-away validates the list belongs to the household (service does), maps `ValueError` for unchecked ids to 422.
- [ ] **Step 4: `task dev:generate`**, run the tests → PASS; ruff; mypy.
- [ ] **Step 5: Commit** `feat(pantry): rest routes for the pantry and put away`.

### Task 4: MCP scope and tools

**Files:**
- Create: `mealie/mcp/tools/pantry.py`
- Modify: `mealie/mcp/scopes.py` (`ALL_SCOPES += ("pantry:write",)`), `mealie/mcp/tools/__init__.py` (import `pantry`), the consent scope labels (`frontend/app/lang/messages/en-US.json` + `fr-FR.json` under the key family the consent page uses for scope names: "Manage the pantry" / "Gérer le garde-manger"), `docs/fork/deploy.md` scope list if it lists scopes.
- Test: `tests/unit_tests/mcp/test_tools_pantry.py` (pattern: `test_tools_shopping.py` with `_as_user`).

**Interfaces:**
- Consumes `PantryService` (Task 2), `run_in_context`, `require_scope`, `McpContext`, `not_found` from `mealie/mcp/errors.py`.
- Produces tools `get_pantry(location: str | None = None)`, `update_pantry(add: list[dict] | None = None, update: list[dict] | None = None, remove: list[str] | None = None)`, `put_away_shopping_items(list_id: str, item_ids: list[str] | None = None)` with the response shapes of spec § 5; impl functions `get_pantry_impl(ctx, location)`, `update_pantry_impl(ctx, add, update, remove)`, `put_away_impl(ctx, list_id, item_ids)`; `_item_dict(item: PantryItemOut, today: date) -> dict` computing `days_since_bought`, `days_since_opened`, `days_until_use_by` (ints or null) and the two shelf-life values from `item.food.extras` when present.

- [ ] **Step 1: Write the failing tests**: `test_get_pantry_orders_and_counts_days` (freeze today via parameter or monkeypatch `date.today` in the module; use_by in 1 day → `days_until_use_by == 1`), `test_get_pantry_reads_shelf_life_from_food_extras`, `test_update_pantry_add_update_remove_in_one_call` (returns `merged_ids` for a merge), `test_update_pantry_requires_scope` (scopes without `pantry:write` → `McpToolError` forbidden), `test_update_pantry_isolated_by_household`, `test_put_away_tool_matches_rest` (same result shape as Task 3), `test_scopes_include_pantry_write` (`"pantry:write" in ALL_SCOPES`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the tools; docstrings per spec § 5 ("Dates are ISO (YYYY-MM-DD). Set opened_on when the user says they opened something. Freshness is your estimate from these dates and the food's shelf life; say so.").
- [ ] **Step 4: Run** `uv run pytest tests/unit_tests/mcp tests/integration_tests/mcp -p no:xdist -q` → all PASS (existing scope tests may enumerate `ALL_SCOPES`; update expectations); ruff; mypy.
- [ ] **Step 5: Commit** `feat(mcp): pantry tools and pantry:write scope`.

### Task 5: Pantry page and shell entry

**Files:**
- Create: `frontend/app/lib/api/user/household-pantry.ts` (`HouseholdPantryApi extends BaseCRUDAPI<PantryItemCreate, PantryItemOut>` with `baseRoute = "/api/households/pantry"`, `itemRoute = id => ...`, plus `putAway(listId: string, itemIds: string[] | null): Promise<RequestResponse<PutAwayResult>>`), `frontend/app/pages/household/pantry/index.vue`, `frontend/app/components/Domain/Pantry/PantryList.vue`, `PantryGroup.vue`, `PantryItemRow.vue`, `PantryQuickAdd.vue`, `PantryItemDialog.vue`, `frontend/app/composables/use-pantry.ts`, `frontend/app/lib/pantry/freshness.ts`
- Modify: `frontend/app/lib/api/client-user.ts` (register `householdPantry`), `frontend/app/components/Layout/AppShell.vue` (rail item "Pantry" → `/household/pantry` after Shop; "+" menu item "Add to pantry" → `/household/pantry?add=1`), en-US + fr-FR keys under `pantry.*`
- Test: `frontend/app/lib/pantry/freshness.test.ts`, `frontend/app/components/Domain/Pantry/PantryList.test.ts`, extend `AppShell.test.ts` (rail has Pantry).

**Interfaces:**
- Consumes types from `~/lib/api/types/household` (generated in Tasks 1 and 3).
- Produces `freshnessLine(item: PantryItemOut, today: Date, t: (key, params?) => string): { text: string; urgent: boolean } | null` implementing the spec § 6 order ("Use by …" urgent when ≤ 2 days or past; else "Opened N days ago"; else "Bought N days ago"; null when no dates); `usePantry()` returning `{ items, byLocation, loading, failed, refresh, add(name), update(id, data), remove(id), markOpened(id) }` with a sequence guard like `usePlannerWeek`; `PantryList` props `{ byLocation: Array<{ location: PantryLocation; items: PantryItemOut[] }>; today: Date }`, emits `edit(item)`, `opened(item)`, `remove(item)`.

- [ ] **Step 1: Write the failing tests**: freshness order and urgency thresholds (use_by today → urgent; use_by in 3 days → not urgent; only bought_on → "Bought 5 days ago"; nothing → null); `PantryList` groups by location in the fixed order Fridge, Freezer, Cupboard, Other and hides empty groups; AppShell rail contains "Pantry".
- [ ] **Step 2: Run** `pnpm exec vitest run app/lib/pantry app/components/Domain/Pantry app/components/Layout` → FAIL.
- [ ] **Step 3: Implement** the page and components (patterns: shop page for the pinned quick add and the kebab, planner for the sequence guard, `role=status` loading/error lines with "Try again"); empty state per spec § 6; saffron only on urgent "Use by" chips (at most the chips; if several rows are urgent they share the one accent purpose).
- [ ] **Step 4: Run** the tests → PASS; `pnpm lint`; screenshots 390/1280 light/dark with items (fridge + cupboard, one urgent) and empty, under `.superpowers/sdd/<workspace>/screenshots/task5-pantry-*.png`.
- [ ] **Step 5: Commit** `feat(ui): pantry page and navigation`.

### Task 6: "Put away" on the shopping list

**Files:**
- Modify: `frontend/app/components/Domain/Shop/ShopBought.vue` (add `DsButton variant="dark" icon="archiveArrowDown"` "Put away", emit `put-away`), `frontend/app/components/Domain/Shop/ShopList.vue` (forward the emit), `frontend/app/pages/shopping-lists/[id].vue` (handler: `api.householdPantry.putAway(listId, null)` → snackbar `shop.put-away-done` "{count} items put away" with action "Open pantry" → `/household/pantry`; then the composable's reload), `frontend/app/lib/icons/icons.ts` if the icon is missing, en-US + fr-FR keys.
- Test: `frontend/app/components/Domain/Shop/ShopBought.test.ts` (button present only when there are bought items; click emits `put-away`), `ShopPage.test.ts` (handler calls `putAway` with `null` and shows the snackbar).

**Interfaces:**
- Consumes `HouseholdPantryApi.putAway` (Task 5).

- [ ] **Step 1: Write the failing tests.** **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `pnpm lint`; in the dev app tick two items, click Put away, confirm the POST returns 200, the items leave the list and appear on the pantry page; screenshot `task6-shop-put-away-390-light.png` and `task6-pantry-after-1280-light.png`.
- [ ] **Step 5: Commit** `feat(ui): put away bought items into the pantry`.

### Task 7: Docs, gates, screenshots

**Files:**
- Modify: `docs/fork/deploy.md` (scopes list + one paragraph "Pantry and freshness"), `docs/superpowers/specs/2026-10-24-pantry-slice-design.md` (append "Implemented" notes for deviations), `README.md` fork header (mention the pantry).

- [ ] **Step 1:** `uv run pytest tests -p no:xdist -q` → PASS (serial, alone). **Step 2:** `task py:check` lint/format/mypy parts → PASS. **Step 3:** `pnpm lint && pnpm exec vitest run && task ui:build` → PASS. **Step 4:** full screenshot pass of Pantry, Shop (with Put away), Connections consent (new scope visible) at 390/1280 light/dark under `screens/`. **Step 5: Commit** `docs: pantry slice`.
