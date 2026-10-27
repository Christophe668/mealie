# Pantry Quantities After Cooking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After cooking, the pantry check proposes each matched item's new quantity (and lets the cook name a
pantry item used instead of a missing recipe food); the finish screen and Claude apply the chosen quantities.

**Architecture:** A pure proposal module (`pantry_usage.py`) turns recipe ingredient lines + pantry items +
scale into per-item proposals, using the existing pint `UnitConverter`. `CookedMealService.pantry_check`
returns those proposals and the unmatched ingredients; `record` accepts a new quantity and a
`replaces_reference_id` per pantry outcome. The HTTP route, MCP tools and the Vue finish screen consume them.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, SQLAlchemy, pint; Nuxt 4 / Vue 3 / TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-27-pantry-quantities-after-cooking-design.md`

## Global Constraints

- No database migration. `grams_each` lives in the food's existing `extras` (string value, parsed as float).
- Small-amount threshold: a computed `used` under **5%** of the pantry item's quantity is not subtracted
  (constant `SMALL_AMOUNT_RATIO = 0.05`).
- The outcome enum stays `used_up` / `some_left`; "untouched" means the item is left out of `pantry`.
- Old clients keep working: `CookedPantryOutcome.quantity = None` and `replaces_reference_id = None` behave
  exactly as today.
- Everything in `record` stays all-or-nothing inside `single_commit` (refusals write nothing).
- After schema changes run `task dev:generate`; never hand-edit `frontend/app/lib/api/types/`.
- New UI strings in `frontend/app/lang/messages/en-US.json`, plus `fr-FR.json` (the fork keeps French for its
  own screens, as in commit cf93e264d). No other locale files.
- Use `uv run` / `task` for every command.

## Review Focus

1. **Real unit names that pint doesn't know** ("gramme", "gousse", "boîte"): `pint` has no "gramme"; the
   unit must resolve through `standard_unit`/`standard_quantity`, then `abbreviation` ("g"), then
   `name`/`plural_name`. Unknown → `units_differ`, never a crash. Test in Task 1.
2. **Pantry item or recipe line without a quantity** (pantry "poivre 0", recipe "poivre" with no food):
   `no_quantity`, item kept at its quantity; a zero-quantity item is not proposed `used_up`. Test in Task 1.
3. **Rounding**: 1000 g − 200 g must be `800`, not `799.9999`; 1 − 1 must be exactly `used_up`. Round
   results to 3 decimals, treat `<= 1e-9` as zero. Test in Task 1.
4. **A substitute that already matches a recipe food, or one listed twice / for an unknown reference**:
   refused with 400 (`ValueError`) before any write. Tests in Tasks 2 and 3.
5. **Old finish-screen payload during deploy** (`{pantryItemId, outcome}` only): still works unchanged.
   Test in Task 3.

---

### Task 1: Proposal engine

**Files:**
- Create: `mealie/services/claude_context/pantry_usage.py`
- Modify: `mealie/schema/household/cooked_meal.py` (add the enums and `PantryProposal`)
- Test: `tests/unit_tests/services_tests/test_pantry_usage.py`

**Interfaces:**
- Produces (schema, `cooked_meal.py`):
  ```python
  class ProposedOutcome(StrEnum): used_up = "used_up"; some_left = "some_left"; none = "none"
  class ProposalReason(StrEnum):
      subtracted, converted, weight_from_note, weight_from_food, units_differ, small_amount, no_quantity
  class PantryProposal(MealieModel):
      pantry_item_id: UUID4
      used: float | None = None            # in the pantry item's unit
      proposed_quantity: float | None = None
      proposed_outcome: ProposedOutcome
      reason: ProposalReason | None = None  # None only with outcome `none`
      replaces_reference_id: UUID4 | None = None
  ```
- Produces (`pantry_usage.py`):
  - `SMALL_AMOUNT_RATIO = 0.05`
  - `weight_from_note(note: str | None) -> float | None` — grams from the first `N g` / `N kg` in the note
    (regex `(\d+(?:[.,]\d+)?)\s*(kg|g)\b`, comma as decimal point), else `None`.
  - `grams_each(food: IngredientFood | None) -> float | None` — `float(food.extras["grams_each"])` when
    present and positive, else `None`.
  - `amount_in_item(lines: list[RecipeIngredient], item: PantryItemOut, scale: float) -> tuple[float | None, ProposalReason]`
  - `propose_for_food(lines: list[RecipeIngredient], items: list[PantryItemOut], scale: float) -> list[PantryProposal]`
    — `items` already in pantry order and already matched to this food.
  - `propose_substitute(line: RecipeIngredient, item: PantryItemOut, scale: float) -> PantryProposal`
    — same rules, no spill, `replaces_reference_id = line.reference_id`.

Rules `amount_in_item` implements (per line, then summed; lines with no quantity are skipped; all skipped →
`(None, no_quantity)`; item quantity `None`/`0` → `(None, no_quantity)`; any remaining line not computable
→ `(None, units_differ)`; reason returned is the most derived one used, in order
`weight_from_food > weight_from_note > converted > subtracted`):
1. Same `unit.id`, or both without unit → `line.quantity * scale`, `subtracted`.
2. Both units resolve to pint units of compatible dimension → `UnitConverter().convert`, `converted`.
   Resolve a unit by: `standard_quantity * standard_unit` when both set; else first of `abbreviation`,
   `name`, `plural_name` that `UnitConverter().parse(x, strict=False)` returns as a pint `Unit`.
3. Line without unit, item unit is mass → pieces × grams (from `weight_from_note(line.note)`, else
   `grams_each(line.food)`) converted to the item unit. Line in mass, item without unit → grams ÷ grams
   each. Reason `weight_from_note` / `weight_from_food`.

`propose_for_food` (spill, from the spec § 4.1):
```python
remaining = 1.0  # fraction of the recipe's need still to take
for item in items:
    need, reason = amount_in_item(lines, item, scale)
    if need is None:                      -> some_left, proposed_quantity=item.quantity, reason
    elif remaining <= 0:                  -> none, reason None
    else:
        take = min(need * remaining, item.quantity)
        if take < SMALL_AMOUNT_RATIO * item.quantity:
              -> some_left, used=take, proposed=item.quantity, small_amount
        else: left = round(item.quantity - take, 3)
              -> used_up (proposed 0) if left <= 1e-9 else some_left (proposed left), reason
        remaining -= take / need
```
A small amount still counts as taken (`remaining` drops), so a second item isn't charged for it.

- [ ] **Step 1: Write the failing tests** (build `RecipeIngredient`, `IngredientUnit`, `IngredientFood`,
  `PantryItemOut` in memory, no DB). Use the chowder's real shapes:

```python
def test_potato_weight_from_note():  # "1 pomme de terre, note 'environ 200 g, en petits dés'" vs 1000 gramme(abbr "g")
    [p] = propose_for_food([potato_line], [potatoes_1000_g], scale=1)
    assert (p.used, p.proposed_quantity, p.proposed_outcome, p.reason) == (200, 800, "some_left", "weight_from_note")

def test_garlic_same_unit_used_up():  # 1 gousse vs 1 gousse (unit pint can't parse)
    [p] = propose_for_food([garlic_line], [garlic_1_gousse], 1)
    assert (p.proposed_quantity, p.proposed_outcome, p.reason) == (0, "used_up", "subtracted")

def test_paprika_units_differ():  # 1 tsp + 0.5 tsp vs 1 boîte
    [p] = propose_for_food([paprika_1_tsp, paprika_half_tsp], [paprika_1_boite], 1)
    assert (p.used, p.proposed_quantity, p.proposed_outcome, p.reason) == (None, 1, "some_left", "units_differ")

def test_oil_small_amount():  # 2 × 1 tablespoon vs 1 litre (standard data on both units)
    [p] = propose_for_food([oil_tbsp, oil_tbsp], [oil_1_l], 1)
    assert (p.proposed_quantity, p.proposed_outcome, p.reason) == (1, "some_left", "small_amount")

def test_sausage_substitute():  # recipe "150 gramme lardon" vs pantry "saucisse de porc 300 gramme"
    p = propose_substitute(lardon_line, sausage_300_g, 1)
    assert (p.used, p.proposed_quantity, p.replaces_reference_id) == (150, 150, lardon_line.reference_id)

def test_scale_doubles_and_lines_sum():  # two 100 g lines, scale 2, item 1000 g → used 400, left 600
def test_spill_across_items_and_untouched_second():  # need 300 g: [200 g, 500 g] → used_up, 400 left;
                                                     # need 100 g: [200 g, 500 g] → 100 left, second "none"
def test_grams_each_from_food_extras():  # line "2" pieces (no note), food.extras {"grams_each": "150"}, item 1 kg → 0.7 kg
def test_weight_from_note_parsing():  # "environ 200 g" → 200; "1,5 kg" → 1500; "200g" → 200; "1 pincée" → None
def test_no_quantity():  # pantry item quantity 0 → some_left, proposed 0, no_quantity (never used_up)
def test_unknown_unit_names_never_raise():  # "gramme" with no abbreviation/standard data vs "kg" → units_differ
```

- [ ] **Step 2: Run** `uv run pytest tests/unit_tests/services_tests/test_pantry_usage.py -v` — Expected:
  FAIL (ImportError).
- [ ] **Step 3: Add the schema types and implement `pantry_usage.py`** per the interfaces above.
- [ ] **Step 4: Run the tests** — Expected: PASS. Then `uv run mypy mealie/services/claude_context/pantry_usage.py`.
- [ ] **Step 5: Commit** `feat(pantry): propose quantities left after cooking`

---

### Task 2: Pantry check returns proposals, unmatched ingredients and substitutes

**Files:**
- Modify: `mealie/schema/household/cooked_meal.py` (`PantryCheckOut`, new `UnmatchedIngredient`)
- Modify: `mealie/services/claude_context/cooked_meal_service.py` (`pantry_check`)
- Modify: `mealie/routes/households/controller_cooked_meal.py` (`substitute` query param)
- Test: `tests/unit_tests/services_tests/test_cooked_meal_service.py`,
  `tests/integration_tests/user_household_tests/test_cooked_meal_routes.py`

**Interfaces:**
- Consumes: Task 1 (`propose_for_food`, `propose_substitute`, `PantryProposal`).
- Produces:
  ```python
  class UnmatchedIngredient(MealieModel):
      reference_id: UUID4
      food: IngredientFood
      substitute_food_ids: list[UUID4] = []   # from food.substitutions[].substitute_food_id, for picker order
  class PantryCheckOut(...):  # existing fields kept
      proposals: list[PantryProposal] = []     # one per item in `items`, same order
      unmatched_ingredients: list[UnmatchedIngredient] = []
  ```
  `CookedMealService.pantry_check(recipe_id, cooked_on, scale=None, substitutes: dict[UUID, UUID] | None = None) -> PantryCheckOut`
  (`substitutes`: ingredient `reference_id` → pantry item id). `items` = matched items followed by substitute
  items. Group recipe lines by food id for `propose_for_food`, using the existing `_food_matcher` per food.
  An ingredient is unmatched when it has a food, no pantry item matches it, and it isn't substituted.
  Refusals: reference not an ingredient-with-food of the recipe → `ValueError`; item not in household →
  `NoEntryFound`; item already matching a recipe food, or used for two references →
  `PantryItemNotInRecipeError` (a `ValueError`).
  Route: `GET .../pantry-check?cooked_on=&scale=&substitute=<ref>:<item>` (repeatable,
  `substitute: list[str] = Query([])`); malformed value → 400.

- [ ] **Step 1: Failing tests**
  - service: `test_pantry_check_proposals_follow_items` (recipe 1 piece potato note "environ 200 g", item
    1000 g of unit with abbreviation "g" → `proposals[0].proposed_quantity == 800`, `len(proposals) == len(items)`)
  - service: `test_pantry_check_lists_unmatched_with_substitute_foods` (food lardon with substitution →
    sausage food; no lardon item → `unmatched_ingredients[0].substitute_food_ids == [sausage_food.id]`)
  - service: `test_pantry_check_with_substitute` (sausage 300 g as substitute for the 150 g lardon line →
    item in `items`, proposal `proposed_quantity == 150`, `replaces_reference_id == ref`, lardon no
    longer in `unmatched_ingredients`)
  - service: `test_pantry_check_refuses_bad_substitutes` (unknown ref → ValueError; item matching a recipe
    food → PantryItemNotInRecipeError; same item twice → PantryItemNotInRecipeError; other household's item → NoEntryFound)
  - route: `test_pantry_check_substitute_param` (200 with proposal) and `test_pantry_check_malformed_substitute` (400)
- [ ] **Step 2: Run** `uv run pytest tests/unit_tests/services_tests/test_cooked_meal_service.py tests/integration_tests/user_household_tests/test_cooked_meal_routes.py -k "pantry_check" -v` — FAIL.
- [ ] **Step 3: Implement** schemas, service, route.
- [ ] **Step 4: Run the same tests, then the full two files** — PASS (existing tests unchanged).
- [ ] **Step 5: Commit** `feat(cook): pantry check proposes quantities and takes substitutes`

---

### Task 3: Record applies quantities and substitutes

**Files:**
- Modify: `mealie/schema/household/cooked_meal.py` (`CookedPantryOutcome`)
- Modify: `mealie/services/claude_context/cooked_meal_service.py` (`_checked_outcomes`, `record`)
- Test: `tests/unit_tests/services_tests/test_cooked_meal_service.py`,
  `tests/integration_tests/user_household_tests/test_cooked_meal_routes.py`

**Interfaces:**
- Produces:
  ```python
  class CookedPantryOutcome(MealieModel):
      pantry_item_id: UUID4
      outcome: PantryOutcome
      quantity: Annotated[float | None, Field(ge=0)] = None   # some_left only; None keeps the current one
      replaces_reference_id: UUID4 | None = None
  ```
  `record`: `some_left` with `quantity` → update the item's quantity (and `opened_on` as today);
  `used_up` with a `quantity` → `ValueError`. An outcome with `replaces_reference_id` is accepted for an item
  of the household not matching the recipe, when the reference is an ingredient-with-food of the recipe;
  same refusals as Task 2's substitutes. `kept_items` returns the updated rows.

- [ ] **Step 1: Failing tests**
  - `test_record_some_left_with_quantity` (1000 → 800, opened_on set)
  - `test_record_some_left_without_quantity_keeps_it` (old payload; quantity unchanged, opened_on set)
  - `test_record_used_up_with_quantity_refused` (ValueError, nothing written: item still there, entry not marked)
  - `test_record_substitute` (sausage via `replaces_reference_id` → 150 left)
  - `test_record_substitute_refusals` (unknown ref; item matching a recipe food; nothing written)
  - route: `test_record_quantity_roundtrip` (201, `keptItems[0].quantity == 800`)
- [ ] **Step 2: Run** `uv run pytest tests/unit_tests/services_tests/test_cooked_meal_service.py -k record -v` — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run both test files** — PASS.
- [ ] **Step 5: Commit** `feat(cook): recording a cooking sets pantry quantities and substitutes`

---

### Task 4: MCP

**Files:**
- Modify: `mealie/mcp/tools/recipes.py` (`get_recipe_impl`, `get_recipe`)
- Modify: `mealie/mcp/tools/pantry.py` (`_parse_outcomes`, `_PANTRY_OUTCOME_KEYS`, `record_meal_cooked` docs)
- Test: `tests/unit_tests/mcp/test_tools_recipes.py`, `tests/unit_tests/mcp/test_tools_pantry.py`

**Interfaces:**
- Consumes: Task 2 `pantry_check(..., scale, substitutes)`; Task 3 `CookedPantryOutcome`.
- Produces:
  - `get_recipe(slug_or_id: str, scale: float | None = None, substitutes: list[dict[str, str]] | None = None)`;
    `substitutes` entries `{reference_id, pantry_item_id}` (unknown keys → `McpToolError`). Each `in_pantry`
    entry gains `used`, `proposed_quantity`, `proposed_outcome`, `reason`, `replaces_reference_id`; the
    response gains `unmatched_ingredients: [{ref, food, substitute_food_ids}]`. Service refusals →
    `McpToolError` with the message.
  - `record_meal_cooked` pantry entries: `{id, outcome, quantity?, replaces_reference_id?}`.
  - Docstrings (exact intent from spec § 4.8): show the proposed changes to the user before recording;
    ask about `unmatched_ingredients` ("did you use something else for X?") and, if so, call `get_recipe`
    again with `substitutes`; send `quantity` for `some_left` items from `proposed_quantity` or the user's
    correction; `proposed_outcome` "none" means leave the item out.
- [ ] **Step 1: Failing tests**: `test_get_recipe_in_pantry_has_proposals`, `test_get_recipe_with_substitutes_and_scale`
  (scale 2 doubles `used`), `test_get_recipe_bad_substitute_key`, `test_record_meal_cooked_quantity_and_substitute`.
- [ ] **Step 2: Run** `uv run pytest tests/unit_tests/mcp -k "get_recipe or record_meal_cooked" -v` — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/unit_tests/mcp -v` — PASS.
- [ ] **Step 5: Commit** `feat(mcp): get_recipe proposes pantry quantities; record_meal_cooked takes them`

---

### Task 5: Finish screen

**Files:**
- Run: `task dev:generate` (regenerates `frontend/app/lib/api/types/household.ts`)
- Modify: `frontend/app/lib/api/user/household-cooking.ts` (`pantryCheck` gains `substitutes`)
- Modify: `frontend/app/components/Domain/Cook/CookPantryCheck.vue` (+ test)
- Modify: `frontend/app/components/Domain/Cook/CookFinish.vue` (+ test)
- Modify: `frontend/app/lang/messages/en-US.json`, `fr-FR.json`

**Interfaces:**
- Consumes: generated `PantryProposal`, `UnmatchedIngredient`, `CookedPantryOutcome` (camelCase).
- Produces:
  - `pantryCheck(recipeId, cookedOn, scale?, substitutes?: Record<string, string>)` — sends one
    `substitute=<ref>:<item>` per entry.
  - `PantryChoices` gains `quantities: Record<string, number>` and `substitutes: Record<string, string>`
    (ref → item id). `CookPantryCheck` props gain `proposals: PantryProposal[]`,
    `unmatched: UnmatchedIngredient[]`, `pantry: PantryItemOut[]` (whole pantry, for the picker); emits
    `update:modelValue` only.
  - `CookFinish`: on mount and whenever `choices.substitutes` changes, calls `pantryCheck` with them, then
    seeds `outcomes`/`quantities` from proposals (`used_up` → used_up; `some_left` → some_left with
    `proposedQuantity`; `none` → nothing), keeping choices already made for items still listed. Loads the
    whole pantry once via `useUserApi().householdPantry.getAll()` (all pages: `perPage = -1` is the default) for the picker. The record body sends
    `quantity` for some_left items whose quantity differs from the item's current one, and
    `replacesReferenceId` for substitute items.
- UI (spec § 4.6): row shows `1000 g → 800 g` when the proposal has a `proposedQuantity` different from the
  current one; chips Used up / Some left; tapping the amount of a some_left row opens a number input (step
  any, min 0, in the item's unit); choosing Some left on a row proposed used_up starts from the current
  quantity; `units_differ` rows show a hint line. Unmatched section: "{food}: not in your pantry" with a
  "Used something else?" button opening a list of pantry items (`substituteFoodIds` foods first, then by
  name); picking sets `substitutes[ref]`; a picked row has a "×" to undo.
- New strings (en-US / fr-FR): `cook.units-dont-compare` "Units don't compare, amount kept" / "Unités
  différentes, quantité gardée"; `cook.not-in-pantry` "{food}: not in your pantry" / "{food} : pas dans le
  garde-manger"; `cook.used-something-else` "Used something else?" / "Autre chose à la place ?";
  `cook.used-instead` "instead of {food}" / "à la place de {food}"; `cook.amount-left` "Amount left" /
  "Quantité restante". (Check `fr-FR.json`'s existing word for pantry and match it.)

- [ ] **Step 1: Run `task dev:generate`**, confirm `PantryProposal` appears in `household.ts`.
- [ ] **Step 2: Failing vitest tests**
  - CookPantryCheck: `shows the proposed amount and preselects the proposed chip` (1000 g → 800 g,
    Some left pressed), `Some left on a used-up proposal starts from the current quantity`,
    `editing the amount updates quantities`, `units_differ row shows the hint`,
    `picking a substitute sets substitutes[ref]`, `"none" proposal has no chip pressed`.
  - CookFinish: `refetches the pantry check with substitutes`, `sends quantity and replacesReferenceId`,
    `an unchanged some_left sends no quantity`.
- [ ] **Step 3: Run** `cd frontend && pnpm test:ci app/components/Domain/Cook` — FAIL.
- [ ] **Step 4: Implement** API client, components, strings.
- [ ] **Step 5: Run** `task ui:check` — PASS (lint + tests).
- [ ] **Step 6: Commit** `feat(cook): finish screen proposes pantry amounts and takes substitutes`

---

### Task 6: Whole-branch check and docs

**Files:**
- Modify: `docs/superpowers/specs/2026-10-27-pantry-quantities-after-cooking-design.md` (add "Implemented
  (date)" section listing deviations, as the cooked-meal spec did)

- [ ] **Step 1: Run** `task py:check` — Expected: format, lint, mypy and pytest all pass.
- [ ] **Step 2: Run** `task ui:check` — PASS.
- [ ] **Step 3: Manual run** (`task py` + `task ui`): cook a recipe with a 1 piece + "environ 200 g" note
  ingredient against a 1000 g pantry item; finish screen shows `1000 g → 800 g`; Done; pantry shows 800 g.
- [ ] **Step 4: Commit** `docs: pantry quantities slice implemented notes`
