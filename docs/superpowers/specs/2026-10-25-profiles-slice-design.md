# Phase 2, slice 3: Household profiles

Date: 2026-10-25. Status: chosen by the builder on Christophe's "continue next phase" (order agreed earlier: feedback, profiles, morning brief). Refines § 4.5 `household_profiles` and the `get_household_context` "preferences" of `2026-10-23-mealie-fork-mcp-design.md`; UI per `2026-10-24-ui-redesign-design.md`.

## 1. What this slice delivers

1. **Who eats here**: one profile per household member (a Mealie user or just a name, for example a child), with diet, allergies, exclusions, dislikes, likes and a free note.
2. **How we cook**: household meal habits: default servings, quick weekdays, maximum cooking time on weeknights and at the weekend, favourite cuisines, and a free note.
3. **Claude uses it**: `get_household_context` returns all of it in `preferences` (the field has been `{}` since phase 1), and `update_household_profile` lets Claude record what it learns ("Sam doesn't eat mushrooms") after asking the user.
4. **A Household screen** to see and edit everything.

Out of scope: linking recipe feedback's free-text "for whom" to profiles (a later slice), automatic allergen detection (Mealie foods carry no allergen data; Claude checks ingredient lists itself).

## 2. Data

`household_member_profiles` (household-scoped, Alembic migration):

| column | type | notes |
|---|---|---|
| id, group_id, household_id | as `recipe_feedback` | NOT NULL scope, indexed |
| user_id | GUID fk `users.id` ondelete SET NULL, nullable | at most one profile per user per household (unique index on household_id, user_id where not null) |
| name | str, NOT NULL | unique per household, case-insensitive (service check) |
| is_child | bool, default false | |
| diet | str enum `none` / `vegetarian` / `vegan` / `pescatarian` / `halal` / `kosher` / `other`, default `none` | |
| allergies, exclusions, dislikes, likes | JSON list of strings, default `[]` | trimmed, de-duplicated case-insensitively, each ≤ 60 chars, ≤ 30 items |
| notes | str, nullable, ≤ 500 chars | |
| position | int, default 0 | display order |
| created_at, updated_at | BaseMixins | |

`household_meal_preferences` (one row per household, created on first write):

| column | type | notes |
|---|---|---|
| id, group_id, household_id | scope; unique household_id | |
| default_servings | int, nullable, 1–20 | |
| quick_weekdays | JSON list of ints 0–6 (0 = Monday), default `[]` | days to keep cooking short |
| weeknight_max_minutes, weekend_max_minutes | int, nullable, 5–480 | |
| favourite_cuisines | JSON list of strings, same normalisation as above | |
| notes | str, nullable, ≤ 500 chars | |

Semantics Claude must follow (in the tool docstrings): **allergies and exclusions are hard constraints** (never propose a recipe whose ingredients contain them; when unsure, check `get_recipe` ingredients or ask); dislikes are soft (avoid unless the user asks); likes and favourite cuisines are hints; quick weekdays and max minutes bound total time on those days.

Security: the two new `Household` relationships are declared with `info={"filterable": False}` (lesson from slice 2), and `User` gets no back-reference to profiles, so no query filter can reach them from groups, households, members or recipes.

## 3. API (under `/api/households`)

- `GET /profile` → `{ "members": [MemberProfileOut], "preferences": MealPreferencesOut | null }`.
- `POST /profile/members` → 201 `MemberProfileOut`; `PUT /profile/members/{id}`; `DELETE /profile/members/{id}`.
- `PUT /profile/preferences` → `MealPreferencesOut` (creates the row when missing).

## 4. MCP

- `get_household_context`: `preferences` becomes `{ "members": [...], "household": {...} | null }`; each member includes `id`, `name`, `is_child`, `diet`, `allergies`, `exclusions`, `dislikes`, `likes`, `notes`, `is_current_user`. Members linked to a Mealie user who are already in `members` (the user list) keep that list unchanged; profiles are separate.
- `update_household_profile(members?: [{id?, name?, user_id?, is_child?, diet?, allergies?, exclusions?, dislikes?, likes?, notes?}], remove_member_ids?: [id], household?: {default_servings?, quick_weekdays?, weeknight_max_minutes?, weekend_max_minutes?, favourite_cuisines?, notes?}, add_to?: {member: name|id, field: "allergies"|"exclusions"|"dislikes"|"likes", values: [str]})` — scope `household:write` (already granted by existing connections). `members` entries with `id` update (partial), without `id` create; `add_to` appends without replacing (the common case: "Sam doesn't like mushrooms"). Validates everything before writing; returns the full updated preferences. Docstring: always confirm with the user before writing; never infer allergies.

## 5. UI

A **Household** page at `/household/profile`, reached from the user menu ("Household") and from Settings.

- **Who eats here**: one card per member, in order: name (with "You" badge when linked to the current user), a child toggle, diet select, and four chip inputs (Allergies, Never serve, Dislikes, Likes; Enter or comma adds a chip, × removes) plus Notes. "Add a person" adds a card; Remove asks for confirmation. Allergy chips are the screen's single saffron element (they are the constraint that matters most), everything else ink/stone.
- **How we cook**: Default servings stepper, quick weekdays as seven toggle buttons (Mon–Sun, respecting the household's first day of week), weeknight and weekend max time selects (15/20/30/45/60/90 minutes, or "No limit"), favourite cuisines chips, Notes.
- Saves per card on "Save" (disabled until changed), with the snackbar on failure; empty state: "Tell Claude who's eating" with "Add yourself" (prefills the current user's name and links the profile).

Copy: sentence case, verbs on buttons, no middle dots; en-US and fr-FR.

## 6. Tests

Unit: normalisation rules, uniqueness (name per household, one profile per user), preferences upsert, add_to append semantics, household isolation, filter opt-out (queryFilter `member_profiles.name` / `meal_preferences.notes` on `/api/groups/households` → 400). Integration: routes. MCP: context shape, update tool (create, partial update, add_to, remove, validation-before-write, scope). Frontend: chip input, card save flow, weekday toggles, empty state.
