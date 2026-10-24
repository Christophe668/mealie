# Phase 2, slice 1: Pantry

Date: 2026-10-24. Status: approved by Christophe ("ok", 2026-10-24) on the proposal below. Refines § 4.5 (`pantry_items`), § 4.6 item 5 ("put the shopping away") and the `get_pantry` / `update_pantry` tools of `2026-10-23-mealie-fork-mcp-design.md`; the UI follows `2026-10-24-ui-redesign-design.md`.

## 1. What this slice delivers

1. A **pantry** per household: what we have, where it is, when it was bought and opened, and an optional "use by" date.
2. **"Put away"** on the shopping list: the bought (ticked) items move into the pantry with today's date and leave the list.
3. **MCP tools** so Claude can read the pantry and keep it up to date, and so it can judge what should be used soon.
4. The pantry **feeds the existing deduction**: a food that is in the pantry counts as "on hand" for Mealie's shopping-list service, so `create_shopping_list_from_mealplan` already skips it (design doc: deduction by presence).

Out of this slice: household profiles, feedback, leftovers, seasonal foods, the morning brief, pantry quantities maths.

## 2. Who estimates freshness

Mealie stores the dates. Claude estimates "still good?" from them with general food knowledge and says so as guidance, never as safety advice; borderline cases are flagged, not decided. To keep estimates consistent, a food can carry a **typical shelf life** (`IngredientFood.extras["shelf_life_days_opened"]` / `["shelf_life_days_unopened"]`, integers, optional; stored in the existing `extras` JSON so no upstream schema change). Claude may fill these in through the existing food API when the user agrees; this slice only reads them into `get_pantry` output.

## 3. Data

`pantry_items` (household-scoped, Alembic migration, SQLite and Postgres):

| column | type | notes |
|---|---|---|
| id | GUID pk | |
| group_id, household_id | GUID fk, indexed | scoping as `group_meal_plan_rules` |
| food_id | GUID fk `ingredient_foods.id`, nullable | linked food when known |
| name | str, not null | display name; the food name when linked, free text otherwise |
| quantity | float, nullable | informational |
| unit_id | GUID fk `ingredient_units.id`, nullable | informational |
| location | str enum `fridge` / `freezer` / `cupboard` / `other`, default `cupboard` | |
| bought_on | date, nullable | |
| opened_on | date, nullable | |
| use_by | date, nullable | from the packaging, or set by the user/Claude |
| source | str enum `shopping` / `manual` / `leftover`, default `manual` | |
| note | str, nullable | |
| created_at, updated_at | from `BaseMixins` | |

Merge rule (used by put-away and by `update_pantry` additions): an incoming item **merges** into an existing pantry item of the same household when they share a `food_id`, or, with no food, the same case-folded `name`. Merging sets `bought_on` to the incoming date (today for put-away), keeps the earlier `opened_on`, adds quantities only when both are numeric and the unit is the same, else keeps the existing quantity and appends the incoming quantity text to `note`. Otherwise a new row is created.

On-hand sync: after any create/merge, the linked food is added to the household's on-hand foods (`households_to_ingredient_foods`); after a removal that leaves no pantry item for that food, it is removed. Foods without a pantry row are never touched, so a household's manual on-hand marks survive.

## 4. API (REST, under the existing `/api/households` router)

- `GET /api/households/pantry` → paginated `PantryItemOut`, default order: `use_by` ascending with nulls last, then `bought_on` descending.
- `POST /api/households/pantry` (`PantryItemCreate`) → 201 `PantryItemOut` (merge rule applies; a merge returns 200 with the merged row).
- `GET /PUT /DELETE /api/households/pantry/{item_id}`.
- `POST /api/households/shopping/lists/{list_id}/put-away` body `{ "item_ids": [..] | null }` (null = every checked item) → `{ "created": [PantryItemOut], "merged": [PantryItemOut], "removed_item_ids": [..] }`. Only checked items are accepted; unchecked ids → 422. The shopping items are deleted afterwards (that is what "put away" means in the UI).

Schemas live in `mealie/schema/household/pantry.py` so `task dev:generate` emits the TypeScript types.

## 5. MCP

- New scope `pantry:write` (name in the consent page: "Manage the pantry"). Existing grants do not have it; the Connections page copy already explains reconnecting.
- `get_pantry(location?: str)` (scope `recipes:read`): items soonest-to-use first, each with `id, name, food_id, quantity, unit, location, bought_on, opened_on, use_by, source, note, days_since_bought, days_since_opened, days_until_use_by, shelf_life_days_opened, shelf_life_days_unopened` (the last two from the food's extras, null when unset).
- `update_pantry(add?: [{name, food_id?, quantity?, unit?, location?, bought_on?, opened_on?, use_by?, note?}], update?: [{id, ...same optional fields}], remove?: [id])` (scope `pantry:write`): applies all three lists in one call, returns the resulting pantry as `get_pantry` does plus `merged_ids` for additions that merged.
- `put_away_shopping_items(list_id, item_ids?: [id])` (scope `pantry:write`): the REST action, same result shape.

Tool docstrings tell Claude: dates are ISO; "opened_on" is what to set when the user says they opened something; freshness is Claude's estimate.

## 6. UI (tokens and Ds* primitives, one saffron element per screen)

- **Pantry page** `/household/pantry`: title "Pantry"; quick-add field pinned like the shop page ("Add to pantry", Enter adds with `source: manual`, `location: cupboard`); items grouped by location (Fridge, Freezer, Cupboard, Other), each row: name, quantity + unit, one secondary line with the most useful fact in this order: "Use by 28 October" (saffron chip when within 2 days or past), else "Opened 3 days ago", else "Bought 5 days ago"; row tap opens a small editor (location, dates, quantity, note); "Opened today" quick action in the row kebab; "Remove" in the kebab. Empty state: "Nothing in the pantry yet" with "Put away your last shop" linking to the open shopping list, or "Add an item".
- **Shell**: rail gains "Pantry" between Shop and the bottom group (the spec reserved it); the mobile tab bar keeps four items; the mobile "+" menu gains "Add to pantry".
- **Shopping list page**: the Bought section gets a `dark` "Put away" button next to "Clear bought items" (saffron stays on the open-count badge). It calls put-away for all checked items, shows a snackbar "12 items put away" with an "Open pantry" action, and reloads the list.
- **Home**: no change in this slice.

Copy: sentence case, verbs on buttons, no middle dots; en-US and fr-FR.

## 7. Tests

Unit: merge rule, on-hand sync both directions, ordering, put-away validation. Integration: the five REST routes and put-away (SQLite; Postgres covered by the existing matrix). MCP: the three tools with scopes enforced and household isolation. Frontend: `PantryList` grouping and the secondary-line rule; `ShopBought` emits `put-away`.
