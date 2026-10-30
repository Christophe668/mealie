# Pantry actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pantry status visible on the recipe page and let a tap on a recipe ingredient or a shopping list item change the pantry or the list in one step.

**Architecture:** Three small backend additions in fork-owned files (optional location on put-away, a shared pantry matcher, two shopping-item endpoints), then frontend: status tokens and a `DsSheet` primitive, a pure status mapper, an ingredient sheet with its actions composable on the recipe page, and a shopping item sheet on the list page.

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy (pytest), Nuxt 4 / Vue 3 / Vuetify 4 (Vitest + @vue/test-utils).

**Spec:** `docs/superpowers/specs/2026-10-30-pantry-actions-design.md`

## Global Constraints

- Strings: add to `frontend/app/lang/messages/en-US.json` and `fr-FR.json` only (fork maintains French). Never touch other locales.
- Members only: nothing new renders for visitors (`isOwnGroup` false) or when `pantry` is null.
- Saffron (`--ds-accent`) is never used for statuses; new tokens `--ds-have`, `--ds-have-surface`, `--ds-missing`, `--ds-missing-surface`, `--ds-soon`, `--ds-soon-surface`; light: have `#2f7a4f` on `#e5f1e9`, missing `#a9432f` on `#f8e6e1`, soon text `#9a6512` on `#fbefd6`, soon bar `#d49a2a`. Dark values: builder's call, ≥ 4.5:1 text contrast.
- Status never by colour alone: tag = icon + word.
- Cook mode (`components/Domain/Cook/*`) and MCP tools (`mealie/mcp/`) do not change. `put_away_shopping_items` behaviour unchanged.
- Python via `uv run --no-sync`; backend run as `python -m mealie.app`; never two pytest processes on the same checkout.
- `task dev:generate` is not reproducible: keep only this change's hunks in generated files.
- No `vue-tsc`: frontend verification is eslint + Vitest.
- Mobile: the sheet fits a 360 px phone in French without horizontal scroll.

## Review Focus

1. A pantry row matched by name only (food-less "Lemons" vs food "lemon") must count as Have on the recipe page **and** as held on the shopping list → test in Task 2 (`test_pantry_match_foodless_name_plural`) and Task 5 status test.
2. Double tap on an action while the request is in flight must not create two pantry rows or two list items → each sheet disables its actions while busy; tests in Tasks 6 and 7 (`ignores a second tap while saving`).
3. Undo after the list or pantry changed meanwhile (item already deleted, row edited) must not crash or resurrect stale data silently → Undo of Used up recreates from snapshot; Undo of Remove recreates; a failing Undo shows an error toast; tests in Tasks 6 and 7 (`undo failure shows an error`).
4. Ingredient with food but no quantity ("salt to taste" with food salt) added to the list → quantity defaults to 1 like the list's own default, never `NaN`/0; test in Task 6 (`adds a quantity-less ingredient as 1`).
5. A shopping item on another household's list → 404 on both new endpoints; test in Task 2 (`test_shopping_pantry_endpoints_foreign_404`).

---

### Task 1: Put-away location override (backend)

**Files:**
- Modify: `mealie/schema/household/pantry.py` (`PutAwayRequest`)
- Modify: `mealie/services/claude_context/pantry_service.py` (`put_away`)
- Modify: `mealie/routes/households/controller_pantry.py` (`HouseholdPutAwayController.put_away`)
- Test: `tests/unit_tests/services_tests/test_pantry_service.py`, `tests/integration_tests/user_household_tests/test_pantry_routes.py`

**Interfaces:**
- Produces: `PutAwayRequest.location: PantryLocation | None = None`; `PantryService.put_away(list_id: UUID, item_ids: list[UUID] | None, today: date | None = None, location: PantryLocation | None = None) -> PutAwayResult`. When `location` is set it replaces `_location_for(item)` for new rows; a merge keeps the existing row's location (merge target selection already prefers same location, then oldest).

- [ ] **Step 1: Write failing tests**
  - service: `test_put_away_location_override` — checked item labelled "Dairy" put away with `location=PantryLocation.freezer` → created row `location == "freezer"`.
  - service: `test_put_away_location_override_merge_keeps_place` — pantry has food X in fridge; put away food X with `location=freezer` → `merged` has one row, `location == "fridge"`, no row created.
  - route: `test_put_away_route_location` — POST `{"itemIds": [id], "location": "freezer"}` → 200, `created[0]["location"] == "freezer"`.
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/unit_tests/services_tests/test_pantry_service.py -k location tests/integration_tests/user_household_tests/test_pantry_routes.py -k location -v` → FAIL.
- [ ] **Step 3: Implement** the field, thread `location` from route to service to `_from_shopping_item(item, today, location)`.
- [ ] **Step 4: Run** the same command → PASS; then the two files in full → PASS.
- [ ] **Step 5: Commit** `feat(pantry): optional location on put-away`

### Task 2: Shared pantry matcher and shopping item pantry endpoints (backend)

**Files:**
- Create: `mealie/services/claude_context/pantry_matching.py`
- Modify: `mealie/services/claude_context/cooked_meal_service.py` (use the shared matcher; behaviour identical)
- Modify: `mealie/services/claude_context/pantry_service.py` (two methods)
- Modify: `mealie/schema/household/pantry.py` (`AlreadyHaveRequest`, `AlreadyHaveResult`)
- Modify: `mealie/routes/households/controller_pantry.py` (two routes on `put_away_router`)
- Test: `tests/unit_tests/services_tests/test_pantry_matching.py` (new), `tests/integration_tests/user_household_tests/test_pantry_routes.py`

**Interfaces:**
- Produces:
  - `food_matcher(foods: list[IngredientFood]) -> Callable[[PantryItemOut], bool]` — moved verbatim from `CookedMealService._food_matcher` (keep `_food_matcher` as a thin alias or replace its call sites).
  - `shopping_item_matcher(item: ShoppingListItemOut) -> Callable[[PantryItemOut], bool]` — with `item.food`: `food_matcher([item.food])`; without: normalised `item.note` (via `IngredientFoodModel.normalize` + `food_name_variants`) against the pantry row's `food.name` when it has a food, else its `name`. Blank note matches nothing.
  - `PantryService.pantry_match(list_id: UUID, item_id: UUID) -> PantryItemOut | None` — first match in `self.pantry.ordered()` order; `NoEntryFound` when list or item is not this household's.
  - `PantryService.already_have(list_id: UUID, item_id: UUID, location: PantryLocation) -> AlreadyHaveResult` — when no match: `add_item(PantryItemCreate(name=<food name or note>, food_id=..., location=location, source=manual))` (no quantity, no bought date); then delete the list item. Pantry row written before the delete.
  - `AlreadyHaveRequest(location: PantryLocation = PantryLocation.cupboard)`; `AlreadyHaveResult(removed_item: ShoppingListItemOut, created_pantry_item: PantryItemOut | None)`.
  - Routes: `GET /households/shopping/lists/{list_id}/items/{item_id}/pantry-match` → `PantryItemOut | None`; `POST /households/shopping/lists/{list_id}/items/{item_id}/already-have` → `AlreadyHaveResult`. Both under `_service_errors()`.

- [ ] **Step 1: Write failing tests**
  - `test_pantry_matching.py`: `food_matcher` by id; food-less row "Lemons" matches food "lemon"; `shopping_item_matcher` food-less note "Lemon" matches pantry row with food "lemons"; blank note matches nothing.
  - routes: `test_pantry_match_none` (empty pantry → `null`), `test_pantry_match_foodless_name_plural` (list item food "lemon", pantry food-less "Lemons" → returns that row), `test_already_have_creates_when_missing` (→ `createdPantryItem.location == "fridge"` when posted `{"location":"fridge"}`, list no longer has the item), `test_already_have_no_create_when_held` (→ `createdPantryItem is None`, pantry count unchanged), `test_shopping_pantry_endpoints_foreign_404` (h2 user on unique_user's list → 404 for both).
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/unit_tests/services_tests/test_pantry_matching.py tests/integration_tests/user_household_tests/test_pantry_routes.py -v` → new tests FAIL.
- [ ] **Step 3: Implement** the module, refactor `cooked_meal_service.py` to import `food_matcher`, add the service methods, schemas and routes.
- [ ] **Step 4: Run** the step 2 command plus `tests/unit_tests/services_tests/ -k "cooked or pantry"` and `tests/integration_tests -k "cooking or pantry"` → PASS (proves the refactor kept the cooked-meal behaviour).
- [ ] **Step 5: Commit** `feat(pantry): shopping item pantry match and already-have endpoints`

### Task 3: Generated types and API client

**Files:**
- Modify (generated, keep only these hunks): `frontend/app/lib/api/types/household.ts`
- Modify: `frontend/app/lib/api/user/household-pantry.ts`

**Interfaces:**
- Consumes: Task 1 and 2 schemas.
- Produces on `api.householdPantry`:
  - `putAway(listId: string, itemIds: string[] | null, location?: PantryLocation | null)` — sends `{ itemIds, location }` (omit `location` when undefined).
  - `pantryMatch(listId: string, itemId: string)` → `requests.get<PantryItemOut | null>`.
  - `alreadyHave(listId: string, itemId: string, location: PantryLocation)` → `requests.post<AlreadyHaveResult>`.

- [ ] **Step 1:** Run `task dev:generate`; `git diff --stat`; revert every hunk not about `PutAwayRequest.location`, `AlreadyHaveRequest`, `AlreadyHaveResult` (`git checkout -p`).
- [ ] **Step 2:** Add the client methods; existing callers of `putAway(id, null)` unchanged. (List items: `api.shopping.items` is `ShoppingListItemsApi`, a `BaseCRUDAPI` with `createOne` / `deleteOne`; no change needed.)
- [ ] **Step 3: Run** `cd frontend && npx eslint app/lib/api/user/household-pantry.ts && npx vitest run` → clean, all pass.
- [ ] **Step 4: Commit** `feat(pantry): api client for location, pantry match, already-have`

### Task 4: Status tokens and `DsSheet`

**Files:**
- Modify: `frontend/app/assets/design/tokens.css` (six tokens, light and dark blocks)
- Create: `frontend/app/components/Design/DsSheet.vue`, `frontend/app/components/Design/DsPlaceChips.vue`
- Test: `frontend/app/components/Design/DsSheet.test.ts`, `frontend/app/components/Design/DsPlaceChips.test.ts`

**Interfaces:**
- Produces: `<DsSheet v-model="open" :title="string" :busy="boolean">` with default slot (body) and optional `#header` slot. Mobile (`useDisplay().mobile`): `v-bottom-sheet`; desktop: `v-dialog max-width="440"`. Focus trapped (Vuetify), Escape closes unless `busy`, `useFocusReturn(open)` like `PantryItemDialog`. Exposes CSS for action rows: class `ds-sheet__action` (button, full width, 48 px min height, icon + label + optional `.ds-sheet__hint` line) and modifier `ds-sheet__action--danger` (`--ds-missing` text).
- Also produces `<DsPlaceChips v-model="location" />` (`components/Design/DsPlaceChips.vue`): a radio group (`role="radiogroup"`, one `role="radio"` button per place, arrow keys move) over `PANTRY_LOCATIONS` from `~/lib/pantry/freshness`, labels `pantry.location.{place}`; selected chip ink-filled (`--ds-text` / `--ds-bg`). `DsChip.vue` is a static label and is not reused.

- [ ] **Step 1: Write failing tests** `DsSheet.test.ts`: renders title and slot when open; emits `update:modelValue` false on Escape; does not close on Escape while `busy`. `DsPlaceChips.test.ts`: renders four radios, the `v-model` one has `aria-checked="true"`, click emits `update:modelValue` with the place.
- [ ] **Step 2: Run** `cd frontend && npx vitest run app/components/Design/DsSheet.test.ts` → FAIL.
- [ ] **Step 3: Implement** tokens and component.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(design): status tokens and DsSheet`

### Task 5: Ingredient status on the recipe page

**Files:**
- Create: `frontend/app/lib/pantry/ingredient-status.ts`
- Test: `frontend/app/lib/pantry/ingredient-status.test.ts`
- Modify: `frontend/app/components/Domain/Recipe/RecipeRead/RecipeReadIngredients.vue`
- Modify: `frontend/app/composables/use-recipe-pantry.ts` (expose `reload()` and `setItems(referenceId, items)` for optimistic updates)
- Strings: `recipe-read.status-have`, `recipe-read.status-soon`, `recipe-read.status-missing`, `recipe-read.add-missing` ("Add {count} to list" / "Ajouter {count} à la liste"); remove now-unused `recipe-read.in-pantry` / `not-in-pantry` only if no other user.

**Interfaces:**
- Produces:
  - `type IngredientStatus = "have" | "soon" | "missing"`
  - `ingredientStatus(items: PantryItemOut[] | undefined, today: Date): IngredientStatus | null` — `undefined` → null (no food / unknown); `[]` → missing; any item with `freshnessLine(...).urgent` → soon; else have.
  - `pantryDetail(items: PantryItemOut[], today, t, locale): string` — "Fridge · use by tomorrow" (places joined ", ", then the most urgent item's freshness text), no "In pantry" prefix.
  - `useRecipePantry` returns `{ pantry, reload, setItems }`.
  - `RecipeReadIngredients` emits `open-ingredient` with `{ ingredient: RecipeIngredient, items: PantryItemOut[] }` and `add-missing` with `RecipeIngredient[]`; new prop `canAct: boolean` (true for members with a known pantry).

- [ ] **Step 1: Write failing tests** `ingredient-status.test.ts`: undefined → null; [] → "missing"; use-by tomorrow → "soon"; use-by in 10 days → "have"; detail for fridge+freezer rows → "Fridge, Freezer · use by …".
- [ ] **Step 2: Run** `npx vitest run app/lib/pantry/ingredient-status.test.ts` → FAIL.
- [ ] **Step 3: Implement** the lib; then the component: remove the tick boxes and `ticks` sessionStorage writes (keep the exported `ingredientTicksKey`, cook mode imports it); each row with a status and `canAct` is a `<button class="read-ingredients__row ds-focus">` whose accessible name is the ingredient text + status word; left 4 px bar and end tag per status; detail line under the text; summary becomes a card "**{have} of {total}** in your pantry" with `DsButton variant="dark"` "Add N to list" when missing > 0 (emits `add-missing`). Rows without status stay plain `<li>` text.
- [ ] **Step 4: Write component test** `RecipeReadIngredients.test.ts`: three ingredients (have, soon, missing) + one without food → three tags with words "Have", "Use soon", "Missing", fourth has no tag and is not a button; clicking the missing row emits `open-ingredient` with its items `[]`; "Add 1 to list" emits `add-missing` with the missing ingredient; with `pantry=null` no tags, no buttons, no summary.
- [ ] **Step 5: Run** both test files → PASS; `npx eslint` on changed files → clean.
- [ ] **Step 6: Commit** `feat(recipe): visible pantry status per ingredient`

### Task 6: Ingredient sheet and its actions

**Files:**
- Create: `frontend/app/composables/use-ingredient-pantry-actions.ts`
- Test: `frontend/app/composables/use-ingredient-pantry-actions.test.ts`
- Create: `frontend/app/components/Domain/Recipe/RecipeRead/RecipeIngredientSheet.vue`
- Test: `frontend/app/components/Domain/Recipe/RecipeRead/RecipeIngredientSheet.test.ts`
- Modify: `frontend/app/components/Domain/Recipe/RecipeRead/RecipeReadPage.vue` (mount the sheet, handle `open-ingredient` and `add-missing`, pass `canAct`)
- Strings (`recipe-ingredient-sheet.*`): `i-have-it`, `i-have-it-hint` ("Put it in the pantry"), `add-to-list`, `running-low`, `running-low-hint`, `opened-today`, `edit`, `used-up`, `used-up-hint`, `not-in-pantry`, `add-use-by`, `pick-list`, toasts `added-to-pantry`, `removed-from-pantry`, `marked-opened`, `added-to-list` ("{item} → {list}"), `added-missing` (plural), `undo-failed`; reuse `general.undo`, `shop.open-pantry`; new `shop.open-list`.

**Interfaces:**
- Consumes: `useRecipePantry().setItems/reload` (Task 5), `DsSheet` (Task 4), `api.householdPantry` CRUD, `api.shopping.items.createOne`, `api.shopping.lists.addRecipes`, `useAddToShoppingListDialog().shoppingLists`.
- Produces `useIngredientPantryActions(opts: { recipeId: () => string; scale: () => number; setItems: (referenceId: string, items: PantryItemOut[]) => void })` returning:
  - `busy: Ref<boolean>`
  - `iHaveIt(ingredient: RecipeIngredient, location: PantryLocation, useBy?: string): Promise<void>` — `createOne({ name: food.name, foodId: food.id, location, useBy, source: "manual" })`; toast + Undo (delete it).
  - `usedUp(ingredient, item: PantryItemOut)` — delete; Undo recreates from the snapshot (same fields, new id).
  - `openedToday(ingredient, item)` — update `openedOn` = today (`yyyy-MM-dd`); Undo restores previous value.
  - `addToList(ingredient, listId: string)` — `api.shopping.items.createOne({ shoppingListId: listId, foodId, unitId, quantity: (ingredient.quantity || 1) * scale, note: ingredient.note || "" })`; toast with **Open list** (`/shopping-lists/{listId}`), no Undo. Running low = same call.
  - `addMissing(ingredients: RecipeIngredient[], listId: string)` — `addRecipes(listId, [{ recipeId, recipeIncrementQuantity: scale, recipeIngredients: ingredients }])`; one plural toast with Open list.
  - Every action: no-op when `busy`; on success calls `setItems` for the ingredient's `referenceId` with the new pantry items; on error toast via `alertUnreportedError`, items unchanged.
- List choice: one list → use it; several → sheet shows a list picker step first; last choice kept in `sessionStorage` key `recipe-read:last-list` and preselected.
- `RecipeIngredientSheet` props `{ ingredient: RecipeIngredient | null; items: PantryItemOut[]; lists: ShoppingListSummary[]; busy: boolean }`, emits the action events; Edit opens `PantryItemDialog` on the chosen row. Several rows → one block per row (place + freshness) with Opened today / Edit / Used up each; Running low once. "Opened today" hidden when `openedOn` is today. Place chips: Fridge, Cupboard, Freezer, Other, preselected `DEFAULT_PANTRY_LOCATION`; "+ use-by" reveals a date input.

- [ ] **Step 1: Write failing composable tests** (mock `useUserApi`, `alert`): `iHaveIt creates a manual pantry item in the chosen place`; `undo of iHaveIt deletes the created item`; `usedUp undo recreates the row`; `openedToday undo restores the previous date`; `addToList scales the quantity` (quantity 2, scale 1.5 → 3); `adds a quantity-less ingredient as 1`; `addMissing sends one addRecipes call with the missing ingredients and the scale`; `ignores a second tap while saving`; `undo failure shows an error`.
- [ ] **Step 2: Run** `npx vitest run app/composables/use-ingredient-pantry-actions.test.ts` → FAIL.
- [ ] **Step 3: Implement** the composable.
- [ ] **Step 4: Write failing sheet tests**: missing ingredient shows "I have it" with four chips (Fridge preselected… per `DEFAULT_PANTRY_LOCATION`) and "Add to shopping list"; held ingredient shows Running low, Opened today, Edit, Used up; opened today hides "Opened today"; two rows render two blocks; with two lists, "Add to shopping list" shows the picker before emitting.
- [ ] **Step 5: Implement** the sheet and wire it into `RecipeReadPage.vue`.
- [ ] **Step 6: Run** both test files and the full suite `npx vitest run` → PASS; eslint clean.
- [ ] **Step 7: Commit** `feat(recipe): ingredient pantry sheet`

### Task 7: Shopping list item sheet

**Files:**
- Create: `frontend/app/components/Domain/Shop/ShopItemSheet.vue`
- Test: `frontend/app/components/Domain/Shop/ShopItemSheet.test.ts`
- Modify: `frontend/app/components/Domain/Shop/ShopItemRow.vue` ("⋯" and long press emit `actions` instead of `edit`; aria-label `shop.item-actions`)
- Modify: `frontend/app/components/Domain/Shop/ShopList.vue`, `ShopAisle.vue`, `ShopBought.vue` (forward `actions`)
- Modify: `frontend/app/pages/shopping-lists/[id].vue` (sheet state and handlers)
- Test: extend `frontend/app/components/Domain/Shop/ShopPage.test.ts`
- Strings (`shop.*`): `item-actions`, `mark-bought`, `mark-not-bought`, `put-away-one`, `put-away-one-hint`, `put-away-into` ("Adds to the one in the {place}"), `already-have`, `already-have-hint`, `edit-quantity-note`, `remove`, toasts `already-have-done`, `put-away-one-done`, `removed` ; reuse `general.undo`, `shop.open-pantry`.

**Interfaces:**
- Consumes: `api.householdPantry.pantryMatch / alreadyHave / putAway(listId, [id], location)` (Task 3), `DsSheet` (Task 4), page's `toggle`, `saveListItem`, `deleteListItem`, `openEditor`, `refresh`, `hasQueuedChanges`.
- Produces: `ShopItemSheet` props `{ item: ShoppingListItemOut | null; match: PantryItemOut | null | undefined /* undefined = loading */; guessedLocation: PantryLocation; busy: boolean }`, emits `toggle`, `put-away(location: PantryLocation)`, `already-have(location: PantryLocation)`, `edit`, `remove`.
- Page handlers:
  - open: set item, `match = undefined`, fetch `pantryMatch`; on error `match = null`.
  - **Mark as bought**: existing `toggle(item)`.
  - **Bought, put it away**: if not checked, `saveListItem({ ...item, checked: true })` and `await refresh()`; abort with `shop.put-away-unsynced` if `hasQueuedChanges`; `putAway(listId, [item.id], match ? undefined : location)`; toast `put-away-one-done` + Open pantry; `refresh()`.
  - **Already in the pantry**: `alreadyHave(listId, item.id, location)`; toast + Undo (recreate list item from `removedItem` via `api.shopping.items.createOne` without `id`; delete `createdPantryItem` if any); `refresh()`.
  - **Edit**: close sheet, `openEditor(item)`.
  - **Remove**: `deleteListItem(item)`; toast + Undo (recreate from snapshot).
  - `guessedLocation`: `guessLocation(labelName: string | undefined): PantryLocation` in `frontend/app/lib/pantry/location-guess.ts`, the same rule as `pantry_service._location_for` (case-insensitive substring; freezer words first, then fridge words, else `cupboard`), word lists copied from `_FREEZER_LABEL_WORDS` / `_FRIDGE_LABEL_WORDS` with a comment pointing at them. Only preselects the chip; the server still receives the chosen place.

- [ ] **Step 1: Write failing tests**
  - `ShopItemSheet.test.ts`: unchecked item shows "Mark as bought"; checked shows "Not bought"; with `match` set, put-away shows "Adds to the one in the fridge" and no chips; with `match=null` shows chips preselected to `guessedLocation`; "Already in the pantry" shows chips only when `match=null`; while `match===undefined` the two pantry actions are disabled.
  - `location-guess.test.ts`: label "Dairy" → fridge, "Frozen" → freezer, "Produce" → cupboard, no label → cupboard.
  - `ShopPage.test.ts`: "⋯" opens the sheet (not the editor); row tap still ticks; already-have calls `alreadyHave` and Undo calls `createOne` and deletes the created pantry row; remove + Undo recreates; `ignores a second tap while saving`.
- [ ] **Step 2: Run** `npx vitest run app/components/Domain/Shop app/lib/pantry/location-guess.test.ts` → FAIL.
- [ ] **Step 3: Implement** row/list event change, sheet, location guess, page handlers.
- [ ] **Step 4: Run** the same → PASS; full `npx vitest run` → PASS; eslint clean.
- [ ] **Step 5: Commit** `feat(shop): item action sheet with pantry actions`

### Task 8: Wrap-up

- [ ] **Step 1:** Backend: `uv run --no-sync pytest tests/unit_tests tests/integration_tests/user_household_tests -q` → PASS; `uv run --no-sync ruff check mealie tests && uv run --no-sync ruff format --check mealie tests` → clean.
- [ ] **Step 2:** Frontend: `cd frontend && npx eslint app && npx vitest run` → clean, all pass.
- [ ] **Step 3:** Add "§ 8 Implemented" to the spec: what shipped, deviations, deferred items.
- [ ] **Step 4: Commit** `docs: pantry actions implemented notes`
