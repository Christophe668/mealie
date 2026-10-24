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
