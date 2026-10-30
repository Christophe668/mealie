# Pantry actions on the recipe page and the shopping list: design

Date: 2026-10-30. Status: draft for approval.

## 1. Intent

Christophe uses the recipe page to check what he has before cooking, and the shopping list while shopping and
putting groceries away. Today the recipe page shows pantry status as a small grey line under each ingredient
("In pantry · Fridge", "Not in pantry"), which is easy to miss, and nothing on it can change the pantry. The
shopping list item offers one action (the tick box), and a tap opens the editor.

He wants:

1. Pantry status on the recipe page that is visible at a glance.
2. A tap on an ingredient (outside cook mode) to say whether it is in the pantry, plus other pantry actions.
3. A tap on a shopping list item to offer more than the tick box: "already in the pantry", "mark as bought",
   "remove", and more.

He approved every action proposed in chat and the mockups (four phone screens: recipe list with tags, sheet
for an ingredient he has, sheet for a missing ingredient, sheet for a shopping list item).

## 2. Goals, non-goals, anti-goals

Goals

- Each ingredient that names a food shows one of three statuses: **Have**, **Use soon**, **Missing**.
- A tap on an ingredient on the recipe page opens an action sheet that changes the pantry or the shopping
  list in one step.
- A tap on a shopping list item (its name or a "⋯" button) opens an action sheet; the tick box stays as the
  one-tap "bought".
- Every action confirms itself in a snackbar. Pantry changes and list removals get **Undo**; adding to a
  shopping list or putting away gets a link instead ("Open list", "Open pantry"), like the bulk Put away
  today (see 4.3 and 4.4 for why).

Non-goals

- Cook mode (`/g/:group/r/:slug/cook`, `components/Domain/Cook/*`) does not change. Its ingredient ticks stay.
- No MCP tool changes. Claude's tools keep their current behaviour.
- No new pantry fields, no new pantry page features.
- No change to the bulk "Put away" on the shopping list page.

Anti-goals (failure even if it works)

- The pantry status gets lost again: small, grey, or only visible on hover.
- An action that changes data without a visible confirmation.
- A sheet that takes more than one tap to do the common thing (I have it, Used up, Mark as bought).
- Saffron used for the statuses: the page's single accent stays on Start cooking (design rule from
  `docs/superpowers/specs/2026-10-24-ui-redesign-design.md`).

## 3. Current state (what this builds on)

- `frontend/app/components/Domain/Recipe/RecipeRead/RecipeReadIngredients.vue` renders the ingredients with a
  tick box per row (ticks kept in sessionStorage under `ingredientTicksKey(slug)`, which cook mode also reads)
  and a pantry line per row from the `pantry` prop. It also shows a "4 of 6 in your pantry" summary.
- `frontend/app/composables/use-recipe-pantry.ts` loads pantry matches per ingredient `referenceId` through
  `api.householdCooking.pantryCheck` (server-side matching, same rule as the end-of-cooking check). Members
  only (`isOwnGroup`).
- `frontend/app/lib/pantry/freshness.ts`: `freshnessLine(item, today, t)` gives the most useful freshness fact
  and `urgent` (use-by within `USE_BY_URGENT_DAYS`).
- Pantry API (`mealie/routes/households/controller_pantry.py`, service
  `mealie/services/claude_context/pantry_service.py`): list, create (merges into an existing row of the same
  food, summing quantities when units match), get, update, delete, and
  `POST /households/shopping/lists/{id}/put-away` with `itemIds` (each must be checked; location is guessed
  from the item's label by `_location_for`).
- Pantry locations: `fridge`, `freezer`, `cupboard`, `other`. `DEFAULT_PANTRY_LOCATION` exists in
  `freshness.ts`.
- `components/Domain/Pantry/PantryItemDialog.vue` edits a pantry item.
- Shopping list page `frontend/app/pages/shopping-lists/[id].vue`: `toggle(item)` ticks with Undo,
  `openEditor(item)` opens `ShoppingListItemEditor`, `putAway()` puts away all checked items.
- `api.shopping.lists.addRecipes(listId, [{ recipeId, recipeIncrementQuantity, recipeIngredients }])` adds a
  recipe's ingredients (optionally a subset) to a list and links the recipe.
  `components/Domain/Recipe/RecipeDialogAddToShoppingList.vue` is upstream's dialog for it.

## 4. Design

### 4.1 Status on the recipe page

Each ingredient row with a pantry match result gets:

- a coloured tag at the end of the row: **✓ Have** (green), **! Use soon** (amber, when any matching pantry
  item is `urgent`), **– Missing** (red);
- a 4 px coloured bar on the row's left edge in the same colour;
- under the ingredient text, the place and freshness in small muted text when it is in the pantry ("Fridge ·
  use by tomorrow"), as today but without the "In pantry" words, which the tag now carries.

Rows whose ingredient names no food, or when the pantry is unknown (`pantry` null: loading, failed, visitor),
show no tag and no bar, as today.

Colours are new design tokens, light and dark variants, defined in `assets/design/tokens.css`:
`--ds-have`, `--ds-have-surface`, `--ds-missing`, `--ds-missing-surface`, `--ds-soon`, `--ds-soon-surface`.
Mockup values (light): have `#2f7a4f` on `#e5f1e9`, missing `#a9432f` on `#f8e6e1`, soon text `#9a6512` on
`#fbefd6` with bar `#d49a2a`. Dark values are the builder's call; they must keep 4.5:1 text contrast. The tag
always pairs colour with an icon and a word, so status never relies on colour alone.

The summary line becomes a card: "**4 of 6** in your pantry" with, when anything is missing, a dark button
**Add N to list** (N = missing count). It adds the missing ingredients (section 4.3).

### 4.2 Recipe page: tick boxes go

Outside cook mode the recipe page no longer has tick boxes; the whole row is a button that opens the
ingredient sheet. Cook mode keeps its ticks; since the recipe page no longer writes them, cook mode simply
starts with whatever it stored. Rows that cannot open a sheet (no food, pantry unknown, visitor) are plain
text, not buttons.

### 4.3 Ingredient sheet

A bottom sheet on mobile, an anchored popover or centred dialog on desktop (builder's call, matching existing
`AppShellMenu` / dialog patterns). Header: food name, the status tag, and a line with the place, opened date
and use-by when known ("Fridge · opened 26 Oct · use by tomorrow"), or "Not in your pantry".

**When missing:**

- **I have it** — creates a pantry item: `name` = food name, `foodId` = the ingredient's food, no quantity,
  `source` = manual, `location` = the selected place chip. Place chips under the action: Fridge, Cupboard,
  Freezer (and Other); preselected `DEFAULT_PANTRY_LOCATION`. A "+ use-by" chip opens a date field before
  saving. Tapping **I have it** with the preselected place saves in one tap.
- **Add to shopping list** — adds this one ingredient to a shopping list as a plain list item (food, unit,
  quantity at the scale currently shown on the recipe page, note), through the list item create endpoint,
  **not** `addRecipes`: a single ingredient must not count the whole recipe on the list (the list page's
  recipe "−" takes off every ingredient of a counted recipe). Subtitle shows "2 lemons → Weekly shop".
  The server may merge it into an existing unchecked item of the same food (raising its quantity); that is
  fine.

**When in the pantry (Have or Use soon):**

- **Running low** — adds the ingredient to a shopping list like above; the pantry is unchanged.
- **Opened today** — sets `openedOn` to today on the pantry item. Hidden when already opened today.
- **Edit place or use-by** — opens `PantryItemDialog` on the pantry item.
- **Used up / not there anymore** (destructive styling) — deletes the pantry item.

When a food matches several pantry items (for example fridge and freezer), the sheet lists them as rows, each
with its place and freshness, and the per-item actions (Opened today, Edit, Used up) apply to the row chosen.
"Running low" applies to the ingredient once.

After any action: the sheet closes, the ingredient's tag updates at once (from the API response), and a
snackbar names what happened. Pantry actions get **Undo**: delete the created pantry item (I have it);
recreate a deleted one from its snapshot (Used up); restore the previous `openedOn` / place / use-by
(Opened today, Edit). Shopping list adds get **Open list** instead of Undo: the add can merge into an
existing item and the create endpoints do not say what they changed, so an exact Undo would need backend
work this feature doesn't justify. On an API error the tag stays as it was and the snackbar shows the error.

**Which shopping list:** with one list, it goes there. With several, the sheet asks once with a list picker
(as `RecipeDialogAddToShoppingList` does). *Builder's call:* remembering the last list used for the session is
fine.

**Add N to list** (summary card) adds all missing ingredients at once with one `addRecipes` call
(`recipeIngredients` = the missing ones, `recipeIncrementQuantity` = the page's current scale), so the list
shows the recipe as the reason, as upstream's "add to shopping list" does. One snackbar with **Open list**.

### 4.4 Shopping list item sheet

The tick keeps its current behaviour (`toggle`, with Undo): today a tap anywhere on the row ticks it
(`ShopItemRow.vue`, the whole row is the checkbox's label), and that stays, since it is the in-store
gesture. The row's existing "⋯" button and its long press, which open the editor today, open the item
sheet instead; the editor moves into the sheet as **Edit**. (Corrected 2026-10-30 while planning: the
first draft assumed a tap opened the editor.) Header: the item's display text, and when
it comes from recipes, "For Roast chicken (Thu)" (recipe names from the item's recipe references; the meal
plan day when known is the builder's call, recipe names alone are enough).

Actions, in this order:

- **Mark as bought** — same as the tick box. Shown as "Not bought" (untick) when already checked.
- **Bought, put it away** — puts this one item into the pantry now: place chips like 4.3, preselected with the
  server's guess for the item (`_location_for`, from its label). Saves the item as checked, then calls
  put-away for that item with the chosen location (backend change, 4.5). The item leaves the list.
  When the pantry already holds this food, put-away merges into that row and keeps its place: the sheet
  then shows no place chips and says where it goes ("Adds to the one in the fridge"). Snackbar with **Open
  pantry**, no Undo, as the bulk Put away (undoing a merge would need the row's previous state).
- **Already in the pantry** — nothing bought. If the pantry already holds this item, the item is deleted
  from the list. If not, a pantry item is created first (`source` manual, chosen place chip, no quantity, no
  bought date), then the list item is deleted. Place chips show only in the second case. "Holds" uses the
  **same matching rule as the recipe page's statuses** (`CookedMealService._food_matcher`: food id, or a
  food-less pantry row matched by name including simple singular/plural), so the two screens never
  disagree and no duplicate row is created. Done server-side in one call (4.5).
- **Edit quantity or note** — opens the existing `ShoppingListItemEditor` (what a tap did before).
- **Remove from list** (destructive styling) — deletes the item.

Snackbars: Mark as bought keeps today's Undo. Remove from list gets **Undo** (recreate the item from its
snapshot). Already in the pantry gets **Undo** (recreate the list item; delete the pantry row if this action
created one; the endpoint returns which). Bought, put it away gets **Open pantry** (above).

To show the right sheet (chips or not) before the tap, the sheet asks the server which pantry row, if any,
holds the item (4.5) when it opens.

### 4.5 Backend change

`PutAwayRequest` gains an optional `location: PantryLocation | None = None`. When set, it overrides
`_location_for` for every item put away in that request. Default behaviour is unchanged, so the bulk Put away
and the MCP tool `put_away_shopping_items` keep working as today. Regenerate the TypeScript types
(`task dev:generate`, keeping only this change's hunks, see the fork's dev notes) and extend
`api.householdPantry.putAway` with the optional location. Add a backend test for the override.

Two small endpoints on the shopping list item, both using `CookedMealService._food_matcher` (or the
matching logic extracted from it into a shared helper) so they agree with the recipe page:

- `GET /households/shopping/lists/{list_id}/items/{item_id}/pantry-match` → the matching pantry item
  (`PantryItemOut`) or `null`. Used by the sheet to choose its wording and whether to show chips.
- `POST /households/shopping/lists/{list_id}/items/{item_id}/already-have` with `{ location }` → deletes the
  list item and, when nothing matched, creates the pantry row; returns `{ removedItem: ShoppingListItemOut,
  createdPantryItem: PantryItemOut | null }` for Undo. Household-scoped like put-away (404 for another
  household's list or item).

Backend tests for the override and both endpoints (matched, not matched, food-less name match, other
household). "I have it", "Opened today", "Used up", "Edit" and "Remove from list" use existing endpoints.

### 4.6 Text

New strings in `en-US.json` and `fr-FR.json` only (the fork maintains French). Suggested French: Have → "En
stock", Use soon → "À utiliser", Missing → "Manquant", I have it → "Je l'ai", Running low → "Bientôt fini",
Opened today → "Ouvert aujourd'hui", Used up → "Fini / plus là", Mark as bought → "Acheté", Bought, put it
away → "Acheté, à ranger", Already in the pantry → "Déjà en réserve", Remove from list → "Retirer de la
liste", Add N to list → "Ajouter N à la liste". Final wording is the builder's call; the tab bar's French
label for the pantry is "Réserve".

## 5. Constraints

- Nuxt 4 / Vue 3 / Vuetify 4, Mise en place design tokens and components (`components/Design/*`); stay
  mergeable with upstream (new code in fork-owned files where possible).
- Members only: visitors of a public group see no statuses and no sheets.
- Mobile first (360 px phone in French must fit the sheet without horizontal scroll); keyboard and screen
  reader usable on desktop (rows are buttons with an accessible name including the status; sheets trap focus
  and close on Escape).
- Frontend tests (Vitest) for the status mapping, each sheet's actions and Undo; backend test for 4.5.
- `vue-tsc` is not installed in the fork; rely on eslint and tests.

## 6. Left to the builder

- Sheet component: a new `Ds` component or an existing dialog, as long as it is a bottom sheet on mobile.
- Dark-mode colour values for the new tokens.
- Icons for each action (from `DsIcon`'s set).
- Whether the last-used shopping list is remembered for the session.
- Exact French wording.

## 7. My calls (not asked of Christophe)

- "Already in the pantry" creates the pantry item when the pantry doesn't list it (he answered "ok" to an
  either/or question; this keeps the pantry truthful).
- Tick boxes leave the recipe page; cook mode keeps them.
- The shopping list row tap stays the one-tap "bought"; "⋯" and long press open the sheet, replacing
  the direct editor.
- Green, red and amber status colours are new to the palette; saffron is not used for them.
- "Bought, put it away" needs a small backend addition (optional location on put-away) rather than
  reimplementing the merge rule in the frontend. When it merges, the existing row's place wins.
- Adding to a shopping list shows "Open list" instead of Undo, and "Bought, put it away" shows "Open
  pantry" instead of Undo; every other action has Undo.
- A single ingredient is added as a plain list item, not as the recipe, so the list doesn't count the
  recipe; "Add N to list" does add it as the recipe. Quantities follow the scale shown on the page.
- "Already in the pantry" uses the recipe page's matching rule, through two small shopping-list endpoints,
  so both screens agree.

## 8. Implemented

Shipped on `t3/pantry-actions` (2026-10-30), commits `e470be469..7b1cd4e56`. Where the code differs from the sections above, or settles something they left open:

**What shipped**

- **Backend.** `PutAwayRequest` takes an optional `location`, which overrides the label-based guess for every item in the request (`e470be469`). `GET /households/shopping/lists/{list_id}/items/{item_id}/pantry-match` returns the matching pantry item or `null`; `POST .../already-have` deletes the list item and creates the pantry row when nothing matched, returning `{ removedItem, createdPantryItem }`. Both use the matching rule shared with the recipe page (`pantry_matching.py`, extracted from `CookedMealService`) and are household-scoped (`18e35deca`).
- **API client and types.** `putAway(listId, ids, location?)`, `pantryMatch`, `alreadyHave` in `household-pantry.ts`; the TypeScript types in `types/household.ts` are hand-written in the generator's style (`6b5aad6c0`).
- **Design system.** Status tokens (have, soon, missing) with light and dark values, plus `DsSheet` (bottom sheet on mobile, dialog on desktop) and `DsPlaceChips` (`84beccf09`, `4ebcdf49b`).
- **Recipe page.** `use-recipe-pantry` and `lib/pantry/ingredient-status.ts` give each ingredient a visible status; the tick boxes are gone (cook mode keeps its own). `RecipeReadIngredients` rows open `RecipeIngredientSheet`, driven by `use-ingredient-pantry-actions` (I have it, running low, opened today, used up, edit, add to list, add N missing to list) (`7b107cf65`, `d8400c863`).
- **Shopping list.** `ShopItemSheet`, opened from the row's "⋯" and long press: mark as bought, bought and put it away, already in the pantry, edit, remove. Strings in `en-US.json` and `fr-FR.json` only (`2bcaacc1f`).
- **Final review fixes** (`7b1cd4e56`): used-up undo no longer duplicates a row, focus is restored after shopping-sheet actions, quantity-less ingredients default to 1 (Ruling F), and five small fixes.

**Deviations from this spec**

- **Row tap (§4.4, corrected during planning).** The row tap stays the one-tap "bought"; only "⋯" and long press open the sheet.
- **Ruling C.** When `pantryMatch` returns a row, "Bought, put it away" sends `location = match.location`, so the row lands in the place the sheet names even if the server's merge rule (same food or exact name) would not merge a name variant. Cost: such a variant can end as a second row in that place.
- **Ruling D.** The TypeScript types are hand-written because codegen does not run in this environment; a later real regeneration may reorder two interfaces.
- **Ruling E.** Light `--ds-soon` is `#8f5d0e` instead of the mockup's `#9a6512`, which gave 4.34:1 on `#fbefd6`, below AA for the 11.5 px tag text. A contrast test pins it.
- **Ruling F.** A quantity-less ingredient is added to a list as quantity 1 at any scale, as "defaults to 1 like the list's own default" says (the plan's formula would have given the scale).
- **Ruling G.** This wrap-up ran after the final review fix wave, so these notes describe what ships.
- **Ruling H.** Undo of "I have it" that the server merged into an existing pantry row restores that row (`updateOne`) instead of deleting it, which §4.3 literally says. Deleting would destroy the user's pre-existing row.

**Known limitations that ship**

- If the local item list is stale, undoing a merged "I have it" deletes the row rather than restoring it (the client cannot detect the merge).
- `refresh()` has an early-return race on focus, and the sheet stays busy during the reload.
- The sub-recipe link is an `<a>` inside the row `<button>` (nested interactive; a link click also opens the sheet).
- `allUnits` is chosen once at setup.
- The list-picker hint lacks the scaled quantity (§4.3's "2 lemons").
- "Add N" with no shopping lists opens upstream's whole-recipe dialog.
- No `RecipeReadPage` wiring test.
- Screen readers are not told why the pantry buttons are disabled while the match loads.
- French "celui" is gendered, and the English "Adds to the one in the other" wording is awkward.
- Server-side leftovers: no route test for an invalid `location` (422) or a food-less already-have create; `AlreadyHaveResult.created_pantry_item` docstring says "created or merged into" though it is only created; the already-have insert and delete are not one transaction (retry is idempotent).

**Owed**

- Manual browser check of the real Vuetify sheet (overlay, focus trap, Escape) and the 360 px French layout (chip wrapping). Component tests cover the behaviour, not the real overlay.
