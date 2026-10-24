# Phase 2, slice 2: Recipe feedback

Date: 2026-10-24. Status: chosen by the builder on Christophe's "continue" after the recommendation "feedback, profiles, morning brief, in that order". Refines § 4.5 `recipe_feedback`, the `record_recipe_feedback` / `get_recipe_feedback` tools and § 4.6 items 3–4 of `2026-10-23-mealie-fork-mcp-design.md`; UI per `2026-10-24-ui-redesign-design.md`.

## 1. What this slice delivers

1. After cooking, the household says how it went: **Loved it / It was fine / Not again**, optionally how much work it was. One tap in cook mode, or one sentence to Claude.
2. Each verdict is kept per household with who cooked, for whom, the date and an optional note. It also updates the recipe's last made date, the cook's own star rating, and adds an entry to Mealie's recipe timeline so it stays visible in upstream screens.
3. Claude sees it: search results and recent meals carry the last verdict, the recipe tool returns recent feedback, and a dedicated tool records and reads feedback. "Not again" recipes are something Claude avoids proposing.
4. The UI shows it: the recipe page gets a "How it went" block, and Home's "Make again" shelf leaves out "Not again" recipes.

Out of scope: household profiles (a later slice links feedback to member profiles; for now "who" is the logged-in user plus an optional free-text "for whom"), editing a past verdict (delete and record again).

## 2. Data

`recipe_feedback` (household-scoped, Alembic migration):

| column | type | notes |
|---|---|---|
| id | GUID pk | |
| group_id, household_id | GUID fk, NOT NULL, indexed | as `pantry_items` |
| recipe_id | GUID fk `recipes.id` ondelete CASCADE, NOT NULL, indexed | |
| user_id | GUID fk `users.id` ondelete SET NULL, nullable | who recorded it |
| for_whom | str, nullable | free text ("Sam", "the kids") |
| made_on | date, NOT NULL | defaults to today |
| verdict | str enum `loved` / `ok` / `never_again`, NOT NULL | |
| effort | int 1–3, nullable | 1 easy, 2 fine, 3 a lot of work |
| note | str, nullable | |
| timeline_event_id | GUID fk `recipe_timeline_events.id` ondelete SET NULL, nullable | |
| created_at, updated_at | BaseMixins | |

Recording, in one service call:
- creates the row (`made_on` defaults to the household's today);
- sets the household's `last_made` for the recipe to `made_on` at 12:00 local, only if that is later than the current value (an old verdict never moves last made backwards);
- sets the recording user's rating: `loved` → 5, `ok` → 3, `never_again` → 1 (favourite flag untouched);
- creates a timeline event `event_type=comment`, subject from the verdict ("Loved it", "It was fine", "Not again", server-side English), message = note, timestamp = `made_on`; stores its id.

Deleting a feedback row deletes its timeline event; last made and rating are left as they are.

Summary per recipe (for lists): `last_verdict`, `last_made_on`, counts per verdict, total.

## 3. API (under `/api/households`)

- `POST /recipe-feedback` (`RecipeFeedbackCreate`: `recipe_id`, `verdict`, `effort?`, `note?`, `for_whom?`, `made_on?`) → 201 `RecipeFeedbackOut`.
- `GET /recipe-feedback?recipeId=&page=&perPage=` → paginated, newest `made_on` first, then newest `created_at`.
- `DELETE /recipe-feedback/{id}` → 200.
- `GET /recipe-feedback/summary?recipeIds=a,b,c` → `{ "<recipe_id>": RecipeFeedbackSummary }` (recipes without feedback omitted; at most 100 ids).

Schemas in `mealie/schema/household/recipe_feedback.py`.

## 4. MCP

No new scope: reading feedback needs `recipes:read`, recording needs `recipes:write` (it writes a rating and a timeline event), so existing connections keep working.

- `record_recipe_feedback(recipe: str, verdict: "loved" | "ok" | "never_again", effort?: 1|2|3, note?: str, for_whom?: str, made_on?: ISO date)` — `recipe` is a slug or id; returns the stored row and the recipe summary.
- `get_recipe_feedback(recipe?: str, limit: int = 10)` — one recipe's feedback, or the household's latest entries across recipes, each with recipe name, slug, verdict, effort, note, for_whom, made_on, recorded_by.
- `search_recipes` and `get_recent_meals` items gain `last_verdict` (null when none); `get_recipe` gains `feedback` (latest 5) and `feedback_summary`.
- Docstrings: `never_again` means do not propose it again unless the user asks; prefer `loved` recipes when the user wants something reliable; record feedback when the user says how a meal went.

## 5. UI

- **Cook mode finish** ("How was it?"): an optional row "How much work?" with three chips "Easy", "Fine", "A lot of work"; the three verdict buttons record feedback (which also sets last made); "Skip" only sets last made, as today. The sessionStorage parking (`pending-feedback:<slug>`) is removed. Visitors keep "Done".
- **Recipe read page**: a "How it went" section in the right column after notes when the recipe has feedback: up to 3 entries, newest first; each entry is the verdict as a short ink label, then one line with the relative date and "for Sam" when set, then the note when set. "See all" opens a dialog listing everything with a delete action per row. No saffron.
- **Home**: "Make again" excludes recipes whose last verdict is `never_again`.

Copy: sentence case, verbs on buttons, no middle dots; en-US and fr-FR.

## 6. Tests

Unit: recording side effects (row, last made only forward, rating mapping, timeline event), delete removes the event, summary counts and ordering, household isolation. Integration: the four routes. MCP: both tools, `last_verdict` in search and recent meals, `feedback` in get_recipe, scope enforcement. Frontend: cook finish posts feedback with effort, Skip keeps the last-made path; "How it went" rendering rules; Make again filter.

## 7. Implemented

Shipped on `feat/feedback` (2026-10-24). Where the code differs from the sections above, or settles something they left open:

1. **Group-wide recipe lookup, poster's household for the data.** A recipe shared by another household of the same group can receive feedback. The service finds the recipe through a group-wide repository (as phase 1's `cross_household_repos`), while the feedback row, the summary, last made and the rating all belong to the poster's household and user, like upstream "I made this". The timeline event goes through the group-level timeline repository, so it is attached to the shared recipe and visible group-wide. A recipe in another group gives 404 (REST) or "recipe not found" (MCP).
2. **Feedback is kept out of query filters.** `RecipeModel.feedback`, `Household.pantry_items` and `Household.recipe_feedback` carry `info={"filterable": False}`. `QueryFilterBuilder` gained a small opt-in check (also on the association-proxy branch): a relationship that carries the flag raises `NonFilterableValueError`, so group-wide lists (`/api/recipes`, `/api/groups/households`, `/api/groups/members`) cannot use `queryFilter` or `orderBy` to probe another household's feedback or pantry. The feedback columns are plain `Mapped` columns. No upstream relationship sets the flag, so upstream behaviour is unchanged. This also closes the pantry half of the leak, which was already on `main`. Upstream's own household relationships (shopping lists, meal plans) remain filterable, as upstream ships them.
3. **Orphans on SQLite.** `RecipeModel.feedback` cascades `all, delete, delete-orphan` in the ORM, because Mealie's SQLite runs without `PRAGMA foreign_keys` and the FK cascade never fires there.
4. **Timeline subjects are English.** "Loved it", "It was fine" and "Not again" are written server-side in English, like the pantry's "Unnamed item". The service publishes no event-bus notification for the timeline event (the upstream timeline route does). Deleting a row removes its timeline event before the row.
5. **Listing.** Because feedback attributes are not filterable, the list uses a repository method `page_newest_first` (made_on, then created_at, then id, all descending; `perPage=-1` returns everything) instead of `page_all` with a query filter. `page` must be ≥ 1 (`page=-1` for the last page is not supported) and `perPage=0` is clamped to 1.
6. **Summary errors.** `GET /recipe-feedback/summary` returns `{}` when `recipeIds` is absent or empty. More than 100 ids, or an invalid UUID, returns 422 with Mealie's `ErrorResponse` detail rather than FastAPI's validation-error list. Duplicate ids count toward the cap.
7. **MCP results.** `get_recipe_feedback` returns `{items, total}`. `last_verdict` is computed with one batched summaries call per tool call. Since meal plan entries share one brief helper, it also appears on `get_mealplan` and `add_mealplan_entries` results, not only on `search_recipes` and `get_recent_meals`. `get_recipe` returns the household's own `feedback` and `feedback_summary`, even for a recipe owned by another household.
8. **Strict MCP inputs.** `record_recipe_feedback` advertises `verdict` (`loved`, `ok`, `never_again`) and `effort` (1, 2, 3) as enums in its JSON schema. Values outside them are refused by the SDK's argument validation; the tool's own checks stay as a second line with clearer messages. `made_on` must be exactly `YYYY-MM-DD` (compact `20261020` and week dates such as `2026-W43-1` are refused). A blank or whitespace-only `note` or `for_whom` is stored as null, and other values are trimmed.
9. **Cook copy reuses the feedback keys.** The cook finish buttons use `recipe-feedback.verdict.*`; the old `cook.loved`, `cook.fine` and `cook.not-again` keys were removed. A shared `RecipeReadFeedbackEntry` row renders entries both in "How it went" and in the "See all" dialog.
10. **Focus return.** A `use-focus-return` composable sends focus back to the opener when the "See all" dialog closes. When the last entry is deleted, the block closes the dialog itself and focus goes to the recipe title. The pantry item dialog uses the same composable. Known gap: in Safari and Firefox, a dialog opened with the mouse restores focus to the fallback or the body, because those browsers do not focus a button on click.
11. **Locales.** New strings are in en-US and fr-FR (`cook.how-much-work` and `recipe-feedback.*`), as § 5 asks, even though upstream leaves non-English locales to Crowdin.
