# TRMNL "Ce soir" screen: design

Date: 2026-11-11. Status: draft for approval.

## 1. Intent

Christophe has a TRMNL e-ink display at home. He wants one screen on it, from Mealie, that answers two
questions at a glance:

1. What are we cooking tonight?
2. Is there anything to buy for it?

Only that: no week view, no full shopping list, no other Mealie data. He chose layout **A, "recipe first"**
from three mockups (recipe as the hero on the left, the missing ingredients on the right).

This follows the fork's principle: Mealie holds the data and does the matching; the TRMNL only draws what it
receives.

## 2. Goals, non-goals, anti-goals

Goals

- A TRMNL private plugin, full-screen view (800×480, 1-bit), showing tonight's planned recipe and what is
  missing for it.
- One read-only Mealie endpoint that returns everything the screen needs, already worked out.
- The template lives in the repo so it is versioned; it is pasted into TRMNL by hand.
- French text on the screen (Christophe's Mealie language).

Non-goals

- No half or quadrant views (mashup layouts) in this version.
- No actions from the screen (the TRMNL can't take input anyway).
- No changes to the meal plan, pantry or shopping list from this feature. Strictly read-only.
- No new MCP tool, no Mealie UI page.
- No TRMNL settings form (choosing the meal type, language, etc.). Defaults are fixed in code.

Anti-goals (a failure even if it technically works)

- Saying **"Rien à acheter"** when something is actually missing. A false "all good" is worse than a cautious
  answer: if the endpoint can't tell, the screen must say so (see 4.3).
- Exposing Mealie more widely than needed to make the screen work.
- Logic in the TRMNL template beyond showing and hiding blocks.

## 3. The screen (layout A)

Approved mockup, in words. Frame 800×480, white background, black ink.

**Left column (~55%)**

- Kicker, small caps: `CE SOIR · MERCREDI 11 NOV.` (French day and date).
- Recipe name, large serif, up to 3 lines, then truncated with "…".
- Facts line: total time (`35 min`), servings (`4 portions`, the planned servings), and the last verdict
  when there is one: `♥ adoré la dernière fois` (loved), `bof la dernière fois` (ok). A "never again" verdict
  shows `✗ pas aimé la dernière fois`.
- Recipe photo below, if available (TRMNL dithers it).

**Right column (~45%), separated by a vertical rule**

- `À ACHETER · N`, then one row per missing ingredient: food name left, scaled quantity and unit right
  (`Lait de coco … 400 ml`). An item that is already on an unchecked shopping list line gets a small
  `(sur la liste)` mark.
- `DÉJÀ LÀ · N`, then one short wrapped line of the foods in the pantry, comma-separated; any of them that
  should be used soon (the pantry's "Use first" rule) in bold.

**Bottom bar**: `Mealie` on the left, `mis à jour HH:MM` on the right (the time the data was produced).

**Other states**

- **Nothing to buy**: the right column becomes a black block `✓ Rien à acheter` with
  `N ingrédients sur N à la maison` under it.
- **Nothing planned tonight**: left column shows `Rien de prévu`; the right column shows `À FINIR VITE` with
  the pantry items to use soon (name and days left, e.g. `épinards (2 j)`), or nothing if there are none.
- **Too many rows**: if the missing list doesn't fit (more than ~8 rows), show the first rows and a final
  `+ N autres` row.

## 4. Behaviour

### 4.1 Which meal is "tonight"

- "Today" is the server's local date (`datetime.now().astimezone().date()`), the same convention the MCP
  tools and pantry service already use.
- Pick by meal type first, whether or not the entry has a recipe, in this order: `dinner`, `side`, `lunch`,
  `snack`, `breakfast`. Within a type, an entry with a recipe wins over a free-text one, then the lowest id.
  So a free-text dinner beats a lunch with a recipe, because "ce soir" is the point. *(My call.)*
- A free-text entry (no recipe): its title is the recipe name, and the right column says
  `Pas de recette liée` (state `no_recipe`).
- Entries already marked cooked (`cooked_at` set) are skipped, so after dinner is recorded the screen falls
  back to "Rien de prévu". *(Builder's call: if this turns out odd in use, it's a one-line change.)*

### 4.2 What counts as "à acheter"

Reuse the existing pantry check, `CookedMealService.pantry_check(recipe_id, cooked_on=today)` in
`mealie/services/claude_context/cooked_meal_service.py`. It already powers the per-ingredient pantry marks on
the recipe page, so the screen and the recipe page always agree.

- **Missing** = its `unmatched_ingredients` (ingredients naming a food that no pantry item matches and no
  substitute stands in for).
- **Already at home** = ingredients in its `ingredients` list with at least one matching pantry item.
- Quantities are the recipe quantities multiplied by the entry's `recipe_scale` (the pantry check already
  picks the scale from the entry).
- An ingredient appearing on several recipe lines with the same food is one row, quantities summed when
  the units match; otherwise the first line's quantity is shown. *(Builder's call.)*
- **"(sur la liste)"**: the missing food appears on an unchecked item of any of the household's shopping
  lists (match by food id).
- **Substitutes**: when an unmatched ingredient has a `substitute_food_ids` entry that the pantry holds, it is
  not "à acheter": it counts as at home and shows in the `DÉJÀ LÀ` line as `yaourt (pour crème)`. This
  matches what the recipe page offers. *(My call.)*
- **Quantities**: an ingredient the pantry holds too little of is "à acheter", with what's left; see
  section 7, answer 1.

### 4.3 Ingredients the check can't judge

Recipe lines without a food (unparsed free text) can't be matched. They must not silently disappear:

- They are counted as `à vérifier`. If there is at least one, the "nothing to buy" state is **not** shown;
  instead the right column shows the missing list (possibly empty) and a last line `+ N à vérifier`.
- Mealie has no "optional" flag, and `RecipeIngredient.title` is a section heading carried by a real
  ingredient line, so every line is judged on its food; nothing is excluded because of `title`. *(My call.)*

### 4.4 Refresh

TRMNL polls the endpoint on the plugin's refresh interval (Christophe sets it in TRMNL; 1 hour suggested).
The endpoint is cheap (one meal plan query + one pantry check), so no caching on the Mealie side.

## 5. How it is built

### 5.1 Mealie endpoint

- `GET /api/households/trmnl/tonight`, under a new controller in `mealie/routes/households/`, inheriting
  `BaseUserController` (so normal user auth applies and the data is scoped to the user's household).
- The logic goes in a service in `mealie/services/claude_context/` (e.g. `trmnl_service.py`), reusing the
  cooked meal service's pantry check.
- **Use soon** (bold in `DÉJÀ LÀ`, and the `À FINIR VITE` list): today this rule exists only in the frontend
  (`frontend/app/lib/pantry/freshness.ts`, `freshnessOf` and `NEEDS_ATTENTION` = past / check / soon). Port it
  to Python next to `shelf_life.py` as a faithful copy, with tests on the same cases as the frontend's; the
  frontend stays as it is. Items whose status is `past` show `(dépassé)` rather than a negative day count;
  `check` shows `(à vérifier)`. *(My call: moving the frontend onto the server version is a later cleanup.)*
- Response schema `TrmnlTonightOut` (extends `MealieOutModel`), in `mealie/schema/household/`. Flat and
  display-ready, so the template only reads it. Roughly:
  - `state`: `"planned" | "nothing_planned" | "no_recipe"`
  - `kicker` (already formatted French day/date), `generated_at` (`HH:MM`)
  - `recipe`: `name`, `total_time` (text or null), `servings` (int or null), `verdict_line` (text or
    null), `image_url` (or null)
  - `to_buy`: list of `{name, quantity}` (quantity already formatted, e.g. `400 ml`, `1 botte`) plus
    `on_list: bool`; `to_buy_more` (int, rows beyond the cap)
  - `at_home`: list of `{name, use_soon: bool}`; `at_home_count`, `ingredient_count`
  - `to_check_count` (4.3)
  - `use_soon`: list of `{name, days_left}` (for "nothing planned")
- French formatting (day names, months, units) is done server-side so the template stays dumb. Keep strings in
  the service, not in the frontend locale files (they aren't UI strings).
- Run `mise run dev:generate` after adding the schema (see the project's dev gotchas about it), keeping only
  this slice's hunks.

### 5.2 TRMNL plugin

- A TRMNL **private plugin**, strategy **Polling**, URL pointing at the endpoint, with a polling header
  `Authorization: Bearer <Mealie API token>`.
- The token is a long-lived Mealie API token created in Christophe's profile (existing Mealie feature). It is
  never committed; he pastes it into the TRMNL plugin settings.
- The full view's markup (TRMNL's Liquid template using the TRMNL design framework classes) is stored at
  `docs/trmnl/tonight-full.liquid`, with a short `docs/trmnl/README.md` on how to set up the plugin.

### 5.3 Reaching Mealie

The endpoint must be reachable by whatever renders the TRMNL screen.

- **TRMNL cloud**: TRMNL's servers call the public URL `https://mealie.christophepecsteen.site`. That host is
  behind Cloudflare Access and a "Block outside Belgium" WAF rule, so this one path needs the same treatment
  as `/mcp`: an Access bypass for `/api/households/trmnl/tonight` and a WAF exception for it. The Mealie
  token still protects it. If the photo is wanted, the recipe image path
  (`/api/media/recipes/<id>/images/...`) needs the same, or the photo is left out.
- **Self-hosted TRMNL server (BYOS) on the LAN**: it calls Mealie on the LAN directly
  (`http://192.168.1.51:9925`), and nothing is opened up.

It's the TRMNL cloud (section 7, answer 2).

## 6. Testing

- Unit tests for the service: picks dinner over lunch; skips cooked entries; free-text entry; nothing
  planned; nothing missing; unparsed lines block the "nothing to buy" state; on-list marking; scaling;
  row cap with `to_buy_more`.
- One integration test for the route: auth required, household scoping (another household's plan isn't
  seen), response shape.
- Manual: render the template in TRMNL's preview with a real response.

## 7. Open

Nothing open. Christophe's answers, 2026-11-11:

1. **Not enough of something in the pantry counts as "à acheter".** The pantry check only tests presence, so
   the service adds a sufficiency step using the check's `proposals` (`used`, `proposed_quantity`, `reason`).
   When the pantry holds less than needed in a comparable unit, the row shows what is needed and what is
   left: `Lait de coco · 400 ml (reste 50 ml)`. When units can't be compared (`units_differ`) or a quantity
   is missing (`no_quantity`), the ingredient counts as at home and adds one to `à vérifier` (4.3), so
   "Rien à acheter" is never shown on a guess. Test cases: enough, short, exactly enough, units differ, no
   quantity, several pantry items of one food adding up.
2. **TRMNL cloud.** The device ("Fridge") runs on trmnl.com, with a playlist that already holds Christophe's
   private plugin "Maison", Kaamelott and "The day ahead". So 5.3's cloud path applies: Cloudflare Access
   bypass and WAF exception for the endpoint, and for the recipe image path if the photo is kept. This
   screen is added to that playlist. The device model isn't recorded: use the TRMNL framework's layout
   classes rather than fixed pixel sizes so the template fits either screen size.

## 8. Calls made without asking

- Meal type beats "has a recipe" when picking tonight's entry (4.1).
- A substitute in the pantry counts as at home (4.2).
- No line excluded for being a section title; no "optional" handling (4.3).
- "Use soon" rule ported to Python as a copy of the frontend's (5.1).

- Layout A details beyond the mockup (verdict wording, `+ N autres`, `+ N à vérifier`).
- Dinner first, cooked entries skipped (4.1).
- Unparsed ingredient lines block "Rien à acheter" (4.3).
- Server-side French formatting; template kept logic-free.
- Endpoint path and schema names.
- 1-hour refresh suggestion.
