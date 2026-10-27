# Pantry quantities after cooking

Date: 2026-10-27. Status: draft for review. Revises the cooked-meal slice
(`2026-10-25-cooked-meal-slice-design.md`), which made "pantry quantity maths" a non-goal.

## 1. Intent

Christophe cooked the corn chowder and expected the pantry to reflect it. It didn't: the finish screen
only offered four items, he marked them "some left", and that only stamps an opened date. Quantities never
move, and the meat he used (pork sausage instead of the recipe's lardons) wasn't offered at all.

What he expected, in his words, for that cooking:

- **Potatoes** 1000 g → 800 g (the recipe says "1 pomme de terre, environ 200 g").
- **Garlic** still there (the pantry said 1 clove, the recipe used 1 clove, but he still has garlic).
- **Smoked paprika** untouched (a teaspoon out of a tin).
- **Meat**: he used half of it (150 g of his 300 g of sausage, standing in for the recipe's lardons).

So: after cooking, the pantry should **propose** the new quantities, worked out from the recipe, and he
glances at them, fixes what's wrong, and saves. The garlic case is why it is a proposal and not automatic:
the pantry's own count can be wrong, and silently deleting something he owns would make him stop trusting
the pantry.

## 2. Goals, non-goals, anti-goals

Goals:

1. The pantry check proposes, per matched pantry item, the quantity left after this cooking, from the
   recipe's quantities and the scale cooked.
2. The finish screen shows those proposals pre-filled ("1000 g → 800 g"); each can be changed in one or two
   taps; saving applies them.
3. "Used instead": for a recipe food with no pantry match, he can pick the pantry item he used in its place,
   and gets a proposal for it too.
4. Claude gets the same proposals through MCP and can send the chosen quantities to `record_meal_cooked`.

Non-goals:

- Tracking small amounts of staples (oil, spices, salt, pepper) precisely. Small deductions are not
  proposed (§ 4.4).
- Changing what ticking a meal done on the planner does (still no pantry change). "How was it?" from Home
  already opens this finish screen.
- Learning or correcting the pantry from habits, shopping, or anything other than a cooking.
- A database migration. Everything fits existing tables (§ 4.2).

Anti-goals (failure even if it technically works):

- The pantry changes without him seeing what changes. Every proposal is shown before saving, in the app
  and (by the existing server instructions) through Claude.
- A wrong guess deletes an item without him seeing "used up" proposed first.
- The finish screen becomes a chore: with correct proposals, saving is still one tap (Done).
- Proposals that are confidently wrong (e.g. "1 tin − 1 tsp = 0 tins"). When it can't compare units, it
  proposes nothing rather than guessing.

## 3. What exists today (for the builder)

- `CookedMealService` (`mealie/services/claude_context/cooked_meal_service.py`): `pantry_check` returns
  matched pantry items (by `food_id`, or by name for items without a food) and per-ingredient matches;
  `record` applies outcomes `used_up` (remove) / `some_left` (set `opened_on` if empty), all in one
  transaction, refusing items that don't match the recipe (`PantryItemNotInRecipeError`).
- Schemas in `mealie/schema/household/cooked_meal.py` (`CookedPantryOutcome`, `PantryCheckOut`, ...).
  Route `GET /households/cooking/{recipe_id}/pantry-check` and the record route in
  `mealie/routes/households/controller_cooked_meal.py`.
- Frontend: `frontend/app/components/Domain/Cook/CookFinish.vue` + `CookPantryCheck.vue` (chips
  "Used up" / "Some left", nothing chosen by default), API in `frontend/app/lib/api/user/household-cooking.ts`.
- MCP: `get_recipe` returns `in_pantry`; `record_meal_cooked` in `mealie/mcp/tools/pantry.py`.
- Units: `IngredientUnit.standard_quantity` / `standard_unit` and `UnitConverter` /
  `merge_quantity_and_unit` (`mealie/services/parser_services/parser_utils/unit_utils.py`, pint), already
  used to merge shopping list items (`shopping_lists.py: can_merge`).
- Foods: `substitutions` (`IngredientFoodSubstitutionModel`, "this food may be replaced by that one") and
  `extras` (key/value, editable on the foods data page).
- The real chowder data: recipe ingredient "1 pomme de terre, note: environ 200 g, en petits dés"; pantry
  "pomme de terre 1000 gramme"; "ail 1 gousse" both sides; "paprika fumé 1 teaspoon" vs pantry "1 boîte";
  "huile d'olive 1 tablespoon" twice vs pantry "1 litre"; recipe "lardon 150 g" vs pantry
  "saucisse de porc 300 gramme" (no food). Pantry "Gruyere" has a different food from the recipe's
  "gruyère" (a data duplicate, see § 6).

## 4. Decisions

### 4.1 The proposal

For each pantry item the check offers, a proposal:

- `used`: the amount this cooking takes, in the pantry item's unit (or `null` when not computable).
- `proposed_quantity`: what's left (`null` when not computable).
- `proposed_outcome`: `used_up` | `some_left` | `none` (nothing taken from this item; see § 4.3 for how
  each shows on screen).
- `reason`: why, so the screen and Claude can say it: `subtracted`, `converted`, `weight_from_note`,
  `weight_from_food`, `units_differ`, `small_amount`, `no_quantity`.

Rules:

- Sum every ingredient line of the same food (the chowder has olive oil twice, paprika twice), times the
  scale cooked.
- `proposed_quantity <= 0` → `used_up` (quantity shown as 0). `> 0` → `some_left` with that quantity.
  Not computable (`units_differ`, `small_amount`, `no_quantity`) → `some_left` with the current quantity.
  Nothing taken by the spill rule → `none`.
- Several pantry items of the same food: take from them in pantry order (soonest use-by first), spilling to
  the next. *(Builder's call, marked as such.)*

### 4.2 Comparing units (in order)

1. Same unit (same `unit_id`, or both without a unit): subtract. ("1 gousse" − "1 gousse".)
2. Both units have standard data of the same dimension (mass/mass, volume/volume): convert with the existing
   `UnitConverter`, result in the pantry item's unit. ("2 tbsp" from "1 L".)
3. Recipe in pieces (no unit), pantry in mass: weight per piece from
   a. the ingredient's note, first "N g" / "N kg" in it ("environ 200 g") → `weight_from_note`;
   b. else the food's extra `grams_each` (a number), if set → `weight_from_food`.
   Pantry in pieces, recipe in mass: same weight, the other way.
4. Otherwise not computable, reason `units_differ` ("1 tsp" vs "1 boîte"). Ingredient or pantry item without a
   quantity → not computable, reason `no_quantity`.

`grams_each` lives in the food's existing `extras`, so no migration. Nothing sets it automatically in this
slice; it can be edited on the foods page. *(My call: keeps the slice small; the note covers the chowder.)*

### 4.3 Outcomes and what each writes

Three chips, plus no chip at all:

- **Used up**: the item is removed.
- **Some left**: the item is kept with the shown quantity (proposed, or edited), and gets `opened_on` = the
  cooking date if it had none.
- **Untouched** (no chip selected; tapping the selected chip clears it, as today): nothing is sent for that
  item, nothing is written.

How proposals map onto them:

- `used_up` → Used up pre-selected.
- `some_left` → Some left pre-selected, with the proposed quantity.
- `units_differ`, `small_amount`, `no_quantity` (the recipe uses it, but no amount is computed) → Some left
  pre-selected with the **current** quantity, so the item is only marked opened, as today. The paprika keeps
  its tin; he can clear the chip to leave it fully untouched.
- Pantry items of the food that nothing was taken from (the spill rule left them alone, e.g. a second sealed
  bag of potatoes) → shown with no chip selected, so they stay untouched unless he picks something.

On the wire there is no `unchanged` outcome: an untouched item is simply left out of `pantry`, as today.
*(My call, settling the reviewer's question: keeps the enum at `used_up` / `some_left` and lets "untouched"
mean what it says.)*

### 4.4 Small amounts

If the computed `used` is under 5% of the pantry item's quantity, treat it as not computable, reason
`small_amount` (2 tbsp of a litre of oil). This is what keeps oil and spices from being nickel-and-dimed.
*(My call; the threshold is a constant.)*

### 4.5 "Used instead"

- Recipe ingredients whose food has no pantry match are listed on the finish screen under the pantry
  section ("lardon: not in your pantry. Used something else?").
- Tapping it opens a picker of pantry items; items whose food is a listed substitute of the recipe food come
  first, then the rest by name.
- The pantry check accepts `substitutes` (ingredient reference id → pantry item id) and returns a proposal
  for that item computed against that ingredient line, by the same rules. The screen refetches when he picks.
- `record` accepts outcomes for substitute items: each carries `replaces_reference_id`, and the item must
  exist in the household and the reference must be an ingredient of this recipe. Otherwise
  `PantryItemNotInRecipeError` as today.
- Choosing a substitute does not save a food substitution. *(My call; it can be a later nicety.)*

### 4.6 Finish screen

- Each item row: name, `1000 g → 800 g` (or the current amount alone when nothing is computed), and the
  chips **Used up** / **Some left**, pre-selected per § 4.3; clearing the chip leaves it untouched. This replaces "nothing
  chosen by default" from the earlier slice: the earlier anti-goal was "no change without the user seeing
  it", and pre-filled proposals on screen keep that.
- Tapping the amount on a "Some left" row edits it (number field, the item's unit). Picking "Some left" on
  a row proposed as used up starts from the current quantity, so the garlic becomes "some left, 1 gousse"
  with one tap, and he can type less.
- A one-line explanation under rows where nothing was computed because of `units_differ` ("units don't compare").
  *(Wording left to the builder. New strings go in en-US; the fork also keeps French strings for its own
  screens, as earlier slices did, e.g. commit cf93e264d.)*
- Done saves everything as shown; Skip still saves without the verdict, as today, with the pantry choices.

### 4.7 API changes

- `PantryCheckOut.items[]` gains the proposal fields (or a parallel `proposals` list keyed by item id;
  builder's choice). New `unmatched_ingredients: [{reference_id, food}]` for § 4.5. Query param
  `substitutes` (repeatable `ref:item`, or a POST variant; builder's choice).
- `CookedPantryOutcome` gains `quantity: float | None` (the new quantity for `some_left`; `None` = keep the
  current one, today's behaviour) and `replaces_reference_id: UUID | None`. The outcome enum is unchanged
  (§ 4.3). Old clients keep working.
- `CookedMealOut.kept_items` reflects updated quantities.
- Run `task dev:generate` for the TypeScript types.

### 4.8 MCP

- `get_recipe` gains optional `scale` (default: the plan entry's scale for today, else 1, as now) and
  `substitutes` (`[{reference_id, pantry_item_id}]`), passed to the same pantry check, so Claude gets the
  server's proposal for "I used the sausage instead" or a doubled cooking rather than doing the arithmetic
  itself. *(My call, settling the reviewer's question: no new tool; Claude already calls `get_recipe` before
  recording.)*
- `get_recipe.in_pantry[]` gains `used`, `proposed_quantity`, `proposed_outcome`, `reason`; the response
  gains `unmatched_ingredients`.
- `record_meal_cooked` pantry entries accept `quantity` and `replaces_reference_id`.
- Tool docs tell Claude: show the proposed changes to the user before recording; ask about unmatched
  ingredients ("did you use something else for the lardons?") and, if so, call `get_recipe` again with
  `substitutes`.

## 5. Tests that must exist

- The chowder, against the real shapes in § 3: potatoes 1000 g → 800 g (`weight_from_note`); garlic
  1 → 0 proposed `used_up`; paprika `some_left` at its current quantity (`units_differ`); oil `some_left` at its current quantity
  (`small_amount`); sausage as
  substitute for lardon 300 g → 150 g.
- Scale 2 doubles `used`; two lines of one food are summed; spill across two pantry items.
- A second pantry item untouched by the spill rule comes back `none` and, left without a chip, is not written.
- MCP `get_recipe` with `substitutes` and `scale` returns the same proposals as the HTTP check.
- `record` with `quantity` updates the item; without it keeps the quantity and sets `opened_on`;
  substitute outside the recipe's references is refused; nothing is written on refusal.
- Finish screen: proposed chip pre-selected; editing an amount sends it; picking a substitute refetches and
  shows its proposal.

## 6. Left to the builder

- Exact response shapes where § 4.7 offers a choice; rounding of displayed quantities (2 decimals max, as the
  current display).
- The unrelated duplicate foods ("Gruyere" / "gruyère") are a data fix, not part of this slice. Mention it
  to Christophe; fixing it is a merge on the foods page.
