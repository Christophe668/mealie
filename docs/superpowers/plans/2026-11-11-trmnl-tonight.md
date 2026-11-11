# TRMNL "Ce soir" screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only Mealie endpoint plus a TRMNL private-plugin template that show tonight's recipe and what is missing for it.

**Architecture:** A new service in `mealie/services/claude_context/trmnl_service.py` picks tonight's entry, runs the existing pantry check, adds a quantity-sufficiency step and returns a flat, display-ready, French-formatted `TrmnlTonightOut`. A thin controller exposes it at `GET /api/households/trmnl/tonight`. The Liquid template in `docs/trmnl/` only shows and hides blocks.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, SQLAlchemy (existing Mealie fork); TRMNL private plugin (Polling strategy, Liquid + TRMNL framework CSS classes).

**Spec:** `docs/superpowers/specs/2026-11-11-trmnl-tonight-design.md`

## Global Constraints

- Strictly read-only: no writes to the meal plan, pantry, shopping lists or feedback.
- "Today" is `datetime.now().astimezone().date()` (server local), injectable as a parameter for tests.
- Screen text is French and produced server-side; the template holds no logic beyond show/hide and loops. These strings live in the service, not in frontend locale files.
- Never show the "nothing to buy" state while `to_check_count > 0` (anti-goal: a false "all good").
- Schemas extend `MealieModel` (this fork has no `MealieOutModel`; follow `mealie/schema/household/cooked_meal.py`).
- Python commands in this worktree: `uv run --no-sync ...`. Never run two pytest processes at once against this checkout (shared SQLite test DB).
- Backend run as `python -m mealie.app` if needed (`mealie/mcp` shadows the `mcp` SDK).
- `mise run dev:generate` / `task dev:generate` is not reproducible: run it with `PRODUCTION=false`, keep only this slice's hunks.
- The Mealie API token is never committed.

## Review Focus

1. **Several pantry items of one food that together are enough** (e.g. two 200 ml cans for 400 ml): must not be "à acheter". Test in Task 2.
2. **An ingredient line with a food but no quantity** (e.g. "sel"): must count as at home with `to_check` +1 when the pantry has it with no quantity, and as "à acheter" with `quantity=None` when the pantry lacks it. Tests in Task 5.
3. **Recipe with `recipe_servings = 0` or no `total_time_seconds`**: facts line must drop those parts, not show "0 portions" / "0 min". Test in Task 3.
4. **Two dinners planned the same day**: deterministic pick (recipe beats free text, then lowest id). Test in Task 4.
5. **Another household's meal plan / pantry**: never visible through the endpoint. Test in Task 6.

---

## File Structure

- Create `mealie/services/claude_context/freshness.py`: Python port of `frontend/app/lib/pantry/freshness.ts` (`freshnessOf`, status rules). One responsibility: how fresh a pantry item is.
- Modify `mealie/services/claude_context/pantry_usage.py`: add `uncovered_fraction`, the sufficiency counterpart of `propose_for_food`.
- Create `mealie/schema/household/trmnl.py`: response schema.
- Create `mealie/services/claude_context/trmnl_format.py`: pure French formatting helpers.
- Create `mealie/services/claude_context/trmnl_service.py`: `TrmnlTonightService`.
- Create `mealie/routes/households/controller_trmnl.py`; modify `mealie/routes/households/__init__.py` to include its router.
- Create `docs/trmnl/tonight-full.liquid`, `docs/trmnl/README.md`.
- Tests: `tests/unit_tests/services_tests/test_freshness.py`, `test_pantry_usage_uncovered.py`, `test_trmnl_format.py`, `test_trmnl_service.py`; `tests/integration_tests/user_household_tests/test_trmnl_routes.py`.

Test helpers: copy the patterns in `tests/unit_tests/services_tests/test_cooked_meal_service.py` (`_service`, `_food`, `_recipe`, pantry creation via `user.repos.pantry_items`, plan entries via `SavePlanEntry`) and `tests/integration_tests/user_household_tests/test_cooked_meal_routes.py` (`_create_recipe`, `_plan`, `_pantry`). Fixture: `unique_user_fn_scoped`.

---

### Task 1: Freshness rule on the server

**Files:**
- Create: `mealie/services/claude_context/freshness.py`
- Test: `tests/unit_tests/services_tests/test_freshness.py`

**Interfaces:**
- Produces:
  - `class FreshnessStatus(StrEnum)`: `past`, `check`, `soon`, `ok`, `unknown`
  - `USE_BY_URGENT_DAYS = 2`
  - `NEEDS_ATTENTION: tuple[FreshnessStatus, ...] = (past, check, soon)`
  - `@dataclass(frozen=True) class Freshness: status: FreshnessStatus; days_left: int | None; estimated: bool; keeps_days: int | None`
  - `def freshness_of(item: PantryItemOut, today: date) -> Freshness`

- [ ] **Step 1: Write the failing tests.** Port every case in `frontend/app/lib/pantry/freshness.test.ts` that exercises `freshnessOf` (same inputs, same expected status/daysLeft), plus at least:
  - `test_use_by_past`: `use_by = today - 1 day` → `status == past`, `days_left == -1`, `estimated is False`
  - `test_use_by_soon_boundary`: `use_by = today + 2` → `soon`; `today + 3` → `ok`
  - `test_estimate_from_opened`: item with `opened_on = today - 3` and a shelf life of `opened_days = 4` → `days_left == 1`, `estimated is True`, `keeps_days == 4`, `status == soon`
  - `test_estimate_check_then_past`: `keeps_days = 4`, `days_left = -1` → `check`; `days_left = -2` → `past` (threshold `max(2, ceil(4/2))`)
  - `test_no_dates_unknown`: no dates → `unknown`, `days_left is None`
  
  Build `PantryItemOut` with a food whose name hits the built-in shelf-life table, or set `shelf_life` after construction is ignored (validator recomputes it): pick names from `shelf_life.py`'s table so `opened_days`/`unopened_days` are known.
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/unit_tests/services_tests/test_freshness.py -v`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement `freshness_of`** as a line-for-line port of `statusFrom` + `freshnessOf` (use-by date first; else opened_on + `opened_days`; else bought_on + `unopened_days`; else unknown). Day difference = `(target - today).days`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: port pantry freshness rule to the server`.

### Task 2: Is the pantry enough? (`uncovered_fraction`)

**Files:**
- Modify: `mealie/services/claude_context/pantry_usage.py` (next to `propose_for_food`, line ~215)
- Test: `tests/unit_tests/services_tests/test_pantry_usage_uncovered.py`

**Interfaces:**
- Produces: `def uncovered_fraction(lines: list[RecipeIngredient], items: list[PantryItemOut], scale: float) -> float | None`
  - Returns the fraction (0..1) of the recipe's need for this food that the items don't cover, using the same spill loop as `propose_for_food` (`amount_in_item` per item, `remaining -= min(need * remaining, item.quantity) / need`).
  - Returns `None` when the answer can't be known: the loop ends with `remaining > _EPSILON` and at least one item gave `need is None` or had no `quantity`.
  - Returns `0.0` when covered (including `small_amount` cases).

- [ ] **Step 1: Write the failing tests** (ml units; build lines/items like the existing pantry_usage tests do, find them with `grep -rln propose_for_food tests`):
  - `test_enough`: need 400 ml, item 500 ml → `0.0`
  - `test_exactly_enough`: 400 vs 400 → `0.0`
  - `test_short`: 400 vs 100 → `pytest.approx(0.75)`
  - `test_two_items_add_up`: 400 vs items 200 + 200 → `0.0`  *(Review Focus 1)*
  - `test_units_differ_unknown`: need 2 pieces, item in ml, no grams_each → `None`
  - `test_item_without_quantity_unknown`: item quantity `None` → `None`
  - `test_scale`: need 200 ml, scale 2, item 300 ml → `pytest.approx(0.25)`
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/unit_tests/services_tests/test_pantry_usage_uncovered.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement `uncovered_fraction`.** Refactor so `propose_for_food` and `uncovered_fraction` share the spill loop if that stays readable; otherwise mirror it. `propose_for_food` behaviour must not change.
- [ ] **Step 4: Run** the new tests and `uv run --no-sync pytest tests/unit_tests/services_tests/test_cooked_meal_service.py -q`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat: tell whether the pantry covers a recipe's need`.

### Task 3: Response schema and French formatting

**Files:**
- Create: `mealie/schema/household/trmnl.py`
- Create: `mealie/services/claude_context/trmnl_format.py`
- Test: `tests/unit_tests/services_tests/test_trmnl_format.py`

**Interfaces:**
- Produces (schema, all `MealieModel`):
  ```python
  class TrmnlState(StrEnum): planned = "planned"; nothing_planned = "nothing_planned"; no_recipe = "no_recipe"
  class TrmnlRecipe(MealieModel): name: str; facts: str; image_url: str | None = None
  class TrmnlToBuy(MealieModel): name: str; quantity: str | None = None; left: str | None = None; on_list: bool = False
  class TrmnlAtHome(MealieModel): name: str; use_soon: bool = False
  class TrmnlUseSoon(MealieModel): name: str; when: str
  class TrmnlTonightOut(MealieModel):
      state: TrmnlState; kicker: str; generated_at: str
      recipe: TrmnlRecipe | None = None
      to_buy: list[TrmnlToBuy] = []; to_buy_more: int = 0
      at_home: list[TrmnlAtHome] = []; ingredient_count: int = 0
      to_check_count: int = 0
      use_soon: list[TrmnlUseSoon] = []
  ```
  `ingredient_count` = number of distinct foods judged (at home + to buy); the template prints "`len(at_home)` ingrédients sur `ingredient_count` à la maison".
- Produces (formatting, pure functions):
  - `def kicker(day: date) -> str` → `"CE SOIR · MERCREDI 11 NOV."` (French day and abbreviated month, uppercase; month abbreviations: JANV. FÉVR. MARS AVR. MAI JUIN JUIL. AOÛT SEPT. OCT. NOV. DÉC.)
  - `def facts_line(total_seconds: int | None, servings: float | None, verdict: FeedbackVerdict | None) -> str` → parts joined by `" · "`: `"35 min"` / `"1 h 10"` (≥ 60 min), `"4 portions"` (`"1 portion"`), verdict `"♥ adoré la dernière fois"` / `"bof la dernière fois"` / `"✗ pas aimé la dernière fois"`. Missing or zero parts are dropped; all missing → `""`.
  - `def quantity_text(quantity: float | None, unit: IngredientUnit | None) -> str | None` → `"400 ml"`, `"1,5 kg"` (French decimal comma, at most one decimal, trailing `,0` dropped), `"2"` without unit; unit uses `abbreviation` when `use_abbreviation` is true and the abbreviation is set, else `name`; `None`/0 quantity → unit name alone or `None`.
  - `def use_soon_text(f: Freshness) -> str` → `past` → `"dépassé"`, `check` → `"à vérifier"`, `soon` → `"aujourd'hui"` (0), `"1 j"`, `"2 j"`.
  - `def clock(now: datetime) -> str` → `"16:00"`.

- [ ] **Step 1: Write the failing tests**, one per function, with the exact strings above, including: `facts_line(None, 0, None) == ""` and `facts_line(2100, 4, FeedbackVerdict.loved) == "35 min · 4 portions · ♥ adoré la dernière fois"` *(Review Focus 3)*; `quantity_text(1.5, kg) == "1,5 kg"`; `quantity_text(400.0, ml) == "400 ml"`; `kicker(date(2026, 11, 11)) == "CE SOIR · MERCREDI 11 NOV."`.
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/unit_tests/services_tests/test_trmnl_format.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the schema module and the formatting module (no locale module dependency; hard-code French names).
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: TRMNL tonight schema and French formatting`.

### Task 4: Service, picking tonight and the empty states

**Files:**
- Create: `mealie/services/claude_context/trmnl_service.py`
- Test: `tests/unit_tests/services_tests/test_trmnl_service.py`

**Interfaces:**
- Consumes: Task 1 `freshness_of`, `NEEDS_ATTENTION`; Task 3 schema and formatters; `repos.meals.get_meals_by_date_range`, `repos.pantry_items.ordered()`, `repos.recipe_feedback.summaries`.
- Produces:
  - `class TrmnlTonightService: def __init__(self, repos: AllRepositories, user: PrivateUser, household: HouseholdInDB)` (same constructor shape as `CookedMealService`)
  - `def tonight(self, today: date | None = None, now: datetime | None = None) -> TrmnlTonightOut`
  - `MEAL_ORDER = (PlanEntryType.dinner, PlanEntryType.side, PlanEntryType.lunch, PlanEntryType.snack, PlanEntryType.breakfast)`; `drink` and `dessert` entries are ignored.
  - `USE_SOON_ROWS = 6`

Behaviour: today's entries (same date range call as `CookedMealService` uses for one day), drop `cooked_at` set, drop types not in `MEAL_ORDER`; sort by (`MEAL_ORDER` index, has-no-recipe, id); take the first. None → `nothing_planned` with `use_soon` = pantry items whose `freshness_of(...).status in NEEDS_ATTENTION`, worst status first then pantry order, capped at `USE_SOON_ROWS`, `when = use_soon_text(...)`, `name` = item name. Free-text → `no_recipe`, `recipe = TrmnlRecipe(name=entry.title, facts="")`. Recipe → `planned`, `recipe.facts = facts_line(recipe.total_time_seconds, entry servings or recipe.recipe_servings × entry.recipe_scale, last_verdict)`; `image_url = f"{settings.BASE_URL}/api/media/recipes/{recipe.id}/images/min-original.webp"` when `recipe.image` is set, else `None`. Ingredient fields are left empty in this task (Task 5 fills them). `kicker = kicker(today)`, `generated_at = clock(now)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_nothing_planned_lists_use_soon`: no entries; pantry has one item with `use_by = today + 1`, one with `use_by = today + 30` → `state == nothing_planned`, `[u.name for u in out.use_soon] == [<first item name>]`, `out.use_soon[0].when == "1 j"`
  - `test_dinner_beats_lunch_with_recipe`: lunch with recipe + free-text dinner titled "Pizza" → `state == no_recipe`, `recipe.name == "Pizza"`
  - `test_two_dinners_recipe_wins`: free-text dinner + recipe dinner → `state == planned`, recipe name matches *(Review Focus 4)*
  - `test_cooked_entry_skipped`: only dinner, `cooked_at` set → `nothing_planned`
  - `test_dessert_ignored`: only a dessert entry → `nothing_planned`
  - `test_planned_facts_and_kicker`: recipe with `total_time_seconds=2100`, `recipe_servings=4`, loved feedback recorded → `recipe.facts == "35 min · 4 portions · ♥ adoré la dernière fois"`, `out.kicker` starts with `"CE SOIR · "`
  - `test_image_url_only_with_image`: recipe without `image` → `recipe.image_url is None`
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/unit_tests/services_tests/test_trmnl_service.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `TrmnlTonightService.tonight` as described; check how servings are stored on plan entries (`ReadPlanEntry`) and use the planned servings when present.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: TRMNL tonight service picks tonight's meal`.

### Task 5: Service, what to buy and what is at home

**Files:**
- Modify: `mealie/services/claude_context/trmnl_service.py`
- Test: `tests/unit_tests/services_tests/test_trmnl_service.py`

**Interfaces:**
- Consumes: `CookedMealService(repos, user, household).pantry_check(recipe_id, cooked_on=today)` (scale comes from the entry), Task 2 `uncovered_fraction`, `repos.group_shopping_list_item` (unchecked items, any list of the household), Task 1 freshness.
- Produces: `TO_BUY_ROWS = 8`; private `_ingredients(...)` filling `to_buy`, `to_buy_more`, `at_home`, `ingredient_count`, `to_check_count` on the `planned` result.

Rules (spec 4.2, 4.3, section 7 answer 1), per recipe line, grouping lines by food id in first-appearance order:

| Case | Bucket |
|---|---|
| Line with no food, with some text (note or original text) | `to_check_count += 1` |
| Line with no food and no text | skipped |
| Food with pantry items (from `pantry_check.ingredients`), `uncovered_fraction == 0` | at home |
| Same, `uncovered_fraction is None` | at home, `to_check_count += 1` |
| Same, `uncovered_fraction > 0` | to buy: `quantity` = scaled recipe quantity of its lines (summed when units match, else first line) via `quantity_text`; `left` = `"reste " + quantity_text(sum of its pantry items' quantities, first item's unit)` |
| Food in `unmatched_ingredients` whose `substitute_food_ids` contains a food present in the pantry | at home, name `"<substitute name> (pour <food name>)"` |
| Food in `unmatched_ingredients` otherwise | to buy, `quantity` as above, `left=None` |

- `on_list` = an unchecked shopping list item of the household has the same `food_id`.
- `at_home[i].use_soon` = any of that food's pantry items has a freshness status in `NEEDS_ATTENTION`.
- Cap: if more than `TO_BUY_ROWS` rows, keep the first `TO_BUY_ROWS - 1` and set `to_buy_more` to the rest.
- Names: the food's `name` (`plural_name` not used).

- [ ] **Step 1: Write the failing tests** (each builds a dinner entry with a recipe for today):
  - `test_missing_food_to_buy`: food not in pantry, 400 ml → `to_buy == [TrmnlToBuy(name=..., quantity="400 ml")]`, `to_check_count == 0`
  - `test_enough_at_home`: pantry 500 ml → `to_buy == []`, `[a.name for a in at_home] == [name]`, `ingredient_count == 1`
  - `test_short_shows_left`: pantry 100 ml for 400 ml → `to_buy[0].quantity == "400 ml"`, `to_buy[0].left == "reste 100 ml"`
  - `test_units_differ_to_check`: pantry item in a unit that can't be compared → at home, `to_check_count == 1`
  - `test_food_without_quantity`: line "sel" with food, no quantity; pantry has sel without quantity → at home, `to_check_count == 1`; pantry lacks it → `to_buy[0].quantity is None` *(Review Focus 2)*
  - `test_unparsed_line_to_check`: a line with only a note and no food → `to_check_count == 1`
  - `test_substitute_counts_at_home`: food with a substitution (see `CreateIngredientFoodSubstitution` usage in `test_cooked_meal_service.py`) whose substitute is in the pantry → `to_buy == []`, `at_home[0].name == "<sub> (pour <food>)"`
  - `test_on_list_mark`: missing food also on an unchecked shopping list item → `to_buy[0].on_list is True`; checked item → `False`
  - `test_cap`: 10 missing foods → `len(to_buy) == 7`, `to_buy_more == 3`
  - `test_scaled_quantity`: entry `recipe_scale = 2`, line 200 ml, missing → `quantity == "400 ml"`
  - `test_use_soon_flag`: pantry item of the food with `use_by = today + 1` → `at_home[0].use_soon is True`
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/unit_tests/services_tests/test_trmnl_service.py -v`. Expected: new tests FAIL.
- [ ] **Step 3: Implement** the rules in the table.
- [ ] **Step 4: Run** the file. Expected: all PASS.
- [ ] **Step 5: Commit** `feat: TRMNL tonight lists what to buy and what is at home`.

### Task 6: Endpoint and generated types

**Files:**
- Create: `mealie/routes/households/controller_trmnl.py`
- Modify: `mealie/routes/households/__init__.py` (add `router.include_router(controller_trmnl.router)` beside `controller_cooked_meal`)
- Test: `tests/integration_tests/user_household_tests/test_trmnl_routes.py`
- Generated: `mealie/schema/household/__init__.py` exports, `frontend/app/lib/api/types/household.ts` (and route test helpers if the generator adds them)

**Interfaces:**
- Consumes: Task 4/5 `TrmnlTonightService.tonight()`.
- Produces: `GET /api/households/trmnl/tonight` → `TrmnlTonightOut`, router `UserAPIRouter(prefix="/households/trmnl", tags=["Households: TRMNL"])`, controller class `HouseholdTrmnlController(BaseUserController)`, route `@router.get("/tonight", response_model=TrmnlTonightOut)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_tonight_requires_auth`: no headers → 401
  - `test_tonight_shape`: plan a dinner recipe today via `_plan` → 200, `json["state"] == "planned"`, keys `kicker`, `generatedAt`, `toBuy`, `atHome`, `toCheckCount` present (camelCase as the API returns)
  - `test_tonight_other_household_not_visible`: user A plans dinner; user B (`unique_user_fn_scoped` vs a second user fixture in another household, see how other household-scoping tests do it, e.g. `grep -rn "other_household\|h2_user" tests/integration_tests | head`) → B gets `state == "nothing_planned"` *(Review Focus 5)*
- [ ] **Step 2: Run** `uv run --no-sync pytest tests/integration_tests/user_household_tests/test_trmnl_routes.py -v`. Expected: FAIL (404).
- [ ] **Step 3: Implement** the controller (pattern: `controller_cooked_meal.py`, `@controller(router)`, `cached_property` service).
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Run codegen** `PRODUCTION=false uv run --no-sync python dev/code-generation/main.py` (or `task dev:generate`), then `git diff --stat` and keep only hunks about `trmnl` / `Trmnl*`; revert unrelated churn with `git checkout -p`.
- [ ] **Step 6: Run** `uv run --no-sync ruff check mealie tests && uv run --no-sync mypy mealie/services/claude_context mealie/routes/households/controller_trmnl.py mealie/schema/household/trmnl.py`. Expected: clean.
- [ ] **Step 7: Commit** `feat: GET /api/households/trmnl/tonight`.

### Task 7: TRMNL template and setup notes

**Files:**
- Create: `docs/trmnl/tonight-full.liquid`
- Create: `docs/trmnl/README.md`

**Interfaces:**
- Consumes: Task 6 JSON. TRMNL polling exposes the response's top-level keys as Liquid variables (camelCase, e.g. `{{ kicker }}`, `{% for item in toBuy %}`); confirm the exact variable access in TRMNL's private plugin docs before writing, and adapt if TRMNL nests the payload.

Template: layout A of the spec, section 3: two columns (`columns`/`column` TRMNL framework classes, no fixed pixel widths), left: `kicker`, `recipe.name` (`title` class, clamp 3 lines), `recipe.facts`, `recipe.imageUrl` as `<img class="image-dither">` when present; right: `À ACHETER · {{ toBuy.size | plus: toBuyMore }}` rows (name, quantity, `left`, `(sur la liste)`), `+ {{ toBuyMore }} autres`, `+ {{ toCheckCount }} à vérifier`; `DÉJÀ LÀ · n` line with `useSoon` names in bold. States: `nothing_planned` (Rien de prévu + À FINIR VITE list), `no_recipe` (Pas de recette liée), nothing to buy (`toBuy.size == 0 and toCheckCount == 0` → black block `✓ Rien à acheter` + "`atHome.size` ingrédients sur `ingredientCount` à la maison"). Title bar: `Mealie` + `mis à jour {{ generatedAt }}`.

README: create a Mealie API token (Profile → API Tokens); TRMNL → Plugins → Private Plugin → strategy Polling, URL `https://mealie.christophepecsteen.site/api/households/trmnl/tonight`, header `Authorization=Bearer <token>`, refresh 60 min; paste `tonight-full.liquid` into the Full markup; add the plugin to the "Fridge" playlist. Cloudflare section: run `dev/cloudflare-access-bypass.sh`-style bypass for path `/api/households/trmnl/tonight` (and `/api/media/recipes/*` if the photo is kept) and add these paths to the "Block outside Belgium" WAF rule's exception, as done for `/mcp` on 2026-10-25.

- [ ] **Step 1: Write the template and README.**
- [ ] **Step 2: Check the template renders** by pasting a real response from Task 6 (`curl` against a local backend with a test token) into TRMNL's markup editor preview, or, if no TRMNL access, by rendering it with the `liquid` Python package against the JSON and opening the HTML. Expected: all four states look like the approved mockup.
- [ ] **Step 3: Commit** `docs: TRMNL tonight template and setup`.

### Task 8: Ship (with Christophe)

Not code; needs Christophe's go-ahead for each outward step.

- [ ] Merge the branch to `main`, push; wait for the `fork-image.yml` image build.
- [ ] Redeploy the NAS stack (Portainer stack 26, endpoint 3, re-pull image).
- [ ] Cloudflare: Access bypass + WAF exception for the path(s) in Task 7's README.
- [ ] Christophe creates the token and the TRMNL plugin; check the device shows the screen.

---

## Self-review notes

- Spec coverage: 3 (layout, states, cap) → Tasks 3, 5, 7; 4.1 → Task 4; 4.2/4.3/7.1 → Tasks 2, 5; 4.4 → Task 7 README; 5.1 → Tasks 1, 3–6; 5.2 → Task 7; 5.3/7.2 → Tasks 7, 8; 6 → tests in each task.
- Spec says `total_time` text; the plan uses `total_time_seconds` formatted, which matches the mockup's "35 min" more reliably.
