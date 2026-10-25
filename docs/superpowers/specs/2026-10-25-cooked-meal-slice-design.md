# "We cooked it": done meals, pantry check and leftovers (phase 2, slice 4)

Date: 2026-10-25. Status: draft for review.

## 1. Intent

Christophe wants the moment a meal is cooked to close the loop: the meal plan shows the meal as done, the
pantry stops listing what was used up, and any leftovers go into the fridge so Claude can suggest eating
them in the next few days. He reaches that moment two ways, and both must work:

- **In cook mode on his phone**, after the last step.
- **Telling Claude** in claude.ai ("we had the carbonara tonight").

Principle of the fork, unchanged: Mealie holds the data, Claude does the reasoning. Nothing in the pantry
changes without the user's answer. Recipe units rarely match pantry units ("200 g spaghetti" against "1
pack"), so Mealie never guesses what is left; it only asks.

## 2. Goals, non-goals, anti-goals

Goals:

1. A meal plan entry can be marked **done**: from cook mode, from Claude, and by a tick on the meal plan page.
2. After cooking, a **pantry check** lists the pantry items this recipe uses. For each, the user picks *used
   up* (the item is removed) or *some left* (kept, marked opened today if it had no opened date). Items left
   untouched are unchanged.
3. **Leftovers**: the same moment can add "N portions" of the dish to the pantry (fridge by default) with a
   use-by date, as a `leftover` pantry item.
4. Claude can do all of the above through MCP, following the user's own instructions about confirming
   (server instructions, unchanged).

Non-goals (this slice):

- Pantry quantity maths (subtracting 200 g from 500 g). Quantities stay informational, as in the pantry slice.
- Planning leftovers as a meal plan entry (`leftover_of_id`, from the original design § 4.5). Claude can
  already add a meal plan entry with free text ("Leftover carbonara") if asked.
- A "skipped" state for meal plan entries. Only done / not done.
- Changing how feedback (verdict, effort) works. Cook mode keeps its "how was it" question; Claude keeps
  `record_recipe_feedback`, called only when the user said how it went.

Anti-goals (failure even if it technically works):

- The pantry changes without the user choosing it (no automatic deduction, no default of "used up").
- The finish screen in cook mode becomes a chore: it must stay one tap per item and skippable as a whole.
- A failure in the pantry or leftover part loses the "done" or "last made", or the reverse.

## 3. What exists today (for the builder)

- `group_meal_plans` (`GroupMealPlan`, `mealie/db/models/household/mealplan.py`): date, entry_type, title,
  text, recipe_id, recipe_scale. No done state.
- Pantry (`pantry_items`, `mealie/services/claude_context/pantry_service.py`, spec
  `2026-10-24-pantry-slice-design.md`): name, food_id, quantity, unit_id, location
  (fridge/freezer/cupboard/other), bought_on, opened_on, use_by, source (`shopping`/`manual`/`leftover`,
  `leftover` already exists and is unused), note. MCP `get_pantry`, `update_pantry`, `put_away_shopping_items`.
- Feedback (`recipe_feedback`, spec `2026-10-24-feedback-slice-design.md`): cook mode's finish screen
  (`frontend/app/components/Domain/Cook/CookFinish.vue`) records a verdict and effort, which also moves
  "last made" forward; "skip" only updates last made. MCP `record_recipe_feedback` (verdict required).
- Household profile habits (`2026-10-25-profiles-slice-design.md`): `default_servings`.
- Cook mode does not know which meal plan entry it was opened from.

## 4. Decisions

### 4.1 Done on the meal plan

- New nullable column on `group_meal_plans`: `cooked_at` (timestamp). Done means `cooked_at` is set.
  Alembic migration, tested on SQLite and PostgreSQL.
- Exposed in the meal plan read schemas and through `task dev:generate` to the frontend types.
- **Which entry a cooked recipe marks** (cook mode and Claude, when no entry id is given): the not-yet-done
  entry of the user's household with the same recipe whose date is closest to the cooking date, within the
  cooking date and the day before (a late dinner logged after midnight). None found: nothing is marked, and
  the answer says so; it is not an error.
- **Meal plan page** (`pages/household/mealplan/planner/view.vue`): each entry gets a done tick. Ticking sets
  `cooked_at` and, for a recipe entry, moves last made forward (it goes through `record_cooked` with no pantry
  outcomes and no leftovers); it opens no dialog, the pantry check lives in cook mode and with Claude.
  Unticking only clears `cooked_at` (last made is left as it is). A done entry is visibly marked (style left to
  the builder, within the Mise en place design system). *(Designer's call.)*
- **Recording twice**: entry matching skips entries already done, and `record_cooked` is refused with a clear
  message ("already recorded as cooked on {date}") when an entry with this recipe already has `cooked_at` on
  the cooking date, so cook mode followed by "we had the carbonara" doesn't add a second leftover. Without
  any plan entry the duplicate can't be detected; the tool description tells Claude to check
  `get_recent_meals` first. *(Designer's call.)*
- `get_mealplan` and `get_recent_meals` include `cooked: true/false` per entry, so Claude knows what was
  actually eaten.

### 4.2 Pantry check

- **Matching** (one service function, used by cook mode and MCP): a pantry item of the user's household
  matches a recipe when its `food_id` is the food of one of the recipe's ingredients, or, for items without a
  food, when its name equals that food's name or its simple singular/plural (reuse `food_name_variants` from
  `recipe_writer.py`), case-insensitively. Ingredients without a food don't match anything.
- **Outcomes** per matched item: `used_up` removes the item; `some_left` keeps it and sets `opened_on` to the
  cooking date if it was empty. Items with no outcome are unchanged.
- The cooking date is the cook's own day (the frontend sends it, as the feedback slice does), never the
  server's date.

### 4.3 Leftovers

- One pantry item per cooking: name "Leftover {recipe name}", `source=leftover`, `quantity` = portions (no
  unit; the note says "portions"), location `fridge` by default (`freezer` allowed), `bought_on` = cooking
  date, `use_by` = cooking date + 3 days in the fridge, + 90 days in the freezer, unless a date is given.
  `food_id` empty.
- **Suggested portions** (shown pre-filled, never saved without the user): recipe servings × the scale cooked
  minus the household's `default_servings`, when both are known and the result is positive; otherwise 0.
  The scale is cook mode's scale there; elsewhere (MCP) it is the `recipe_scale` of the meal plan entry the
  cooking would mark (§ 4.1), else 1. *(Designer's call.)*
- Leftovers are ordinary pantry items afterwards: Claude sees them in `get_pantry` (soonest use-by first,
  as today), and they are eaten/removed like any item.

### 4.4 One "cooked" operation

A single service operation records a cooking, so cook mode and Claude behave the same:

`record_cooked(recipe, cooked_on, meal_plan_entry_id?, pantry_outcomes?, leftovers?, feedback?)`:

1. checks everything first (recipe visible to the user, pantry items belong to the household and match the
   recipe, leftover portions 1-50, location fridge/freezer), so a refused call writes nothing;
2. sets last made (as "skip" does today);
3. marks the meal plan entry done (§ 4.1);
4. applies the pantry outcomes and adds the leftover item.

Steps 2-4 commit together; if any fails, nothing is kept and the error says so.
`feedback` (verdict, optional effort) is optional and only used by cook mode: when present, the feedback is
recorded by the existing feedback service inside the same transaction, so cook mode makes one request and a
retry never creates a second feedback row. Claude keeps calling `record_recipe_feedback` separately, only when
the user said how it went. *(Designer's call.)*

REST: an endpoint under the household routes for this operation, plus one to read the matching pantry items
and the suggested leftover portions for a recipe and scale. Naming and shapes left to the builder, following
the controller/service pattern.

### 4.5 Cook mode

The finish screen (`CookFinish.vue`) keeps "how was it" first, but a verdict becomes a selection instead of
saving on tap. Below it, when the recipe has matching pantry items, a "From your pantry" list: each item with
two choices, *Used up* / *Some left*, nothing chosen by default. Then "Leftovers" with a portions stepper
(pre-filled per § 4.3) and Fridge/Freezer. One **Done** button at the bottom saves everything in a single
`record_cooked` call (with the verdict, if one was picked); the existing "skip" still leaves without a verdict
but also saves the pantry choices and leftovers. If the call fails, the screen stays and offers a retry. With
no matching pantry items and no suggested leftovers, the screen looks as today plus the Done button.
*(Designer's call.)* Layout left to the
builder, mobile first, Mise en place components.

### 4.6 MCP

- `get_recipe` gains `in_pantry`: the matching pantry items (id, name, quantity, unit, location, opened_on,
  use_by) and `suggested_leftover_portions`. Scope `recipes:read`, as `get_pantry`.
- New tool `record_meal_cooked(recipe, cooked_on?, meal_plan_entry_id?, pantry?: [{id, outcome}],
  leftover_portions?, leftover_location?, leftover_use_by?)` wrapping § 4.4. Scope `pantry:write`
  (existing; no reconnect). It also writes last made and the meal plan's done state, which elsewhere sit
  behind `recipes:write` and `mealplan:write`; a single scope is a deliberate choice for a one-user install
  whose connection holds all scopes. *(Designer's call.)* Its description tells Claude: call it when the user says a meal was cooked;
  ask about the pantry items and leftovers unless the user's instructions say otherwise; call
  `record_recipe_feedback` too only if the user said how it went.
- Returns what changed: the entry marked done (or none found), items removed/kept, the leftover item.
- Docs: `docs/fork/deploy.md` tool list and a short "After cooking" section.

## 5. Left to the builder

Endpoint names and payload shapes, component structure, the done-tick and done-entry styling, error
wording (plain English, like the existing tools), and test layout, following the patterns of the pantry and
feedback slices.
