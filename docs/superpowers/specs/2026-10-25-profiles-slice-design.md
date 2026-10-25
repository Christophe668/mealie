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

## 7. Implemented

Shipped on `feat/profiles` (2026-10-25) in `80e20c5e3` (models, migration `8e849a1153cf`, schemas, repositories), `6ab03a944` and `aae95781d` (service), `35258f8a7` and `698917b55` (REST), `6e9d848e0` and `d95ef4a08` (MCP), `d4f24249c`, `aae999e14`, `141866e49` and `ab9b4f556` (Household page), and the docs commit. Where the code differs from the sections above, or settles something they left open:

1. **One profile per user is a plain unique constraint.** `household_member_profiles_household_id_user_id_key` on `(household_id, user_id)` replaces § 2's partial unique index: NULLs never collide on SQLite or PostgreSQL, so unlinked members are unaffected. The service checks the rule first; the constraint backs it against a concurrent request, and its violation is reported as "This user is already linked to another member." (409 on REST, a tool error on MCP). That mapping recognises the constraint by name on PostgreSQL and by its column list on SQLite; the profile tests, including a real constraint race, pass on both (PostgreSQL 17, migrated from scratch to `8e849a1153cf`). The name rule is a service check only, so two concurrent creates of the same name can both succeed.
2. **Write rules.** Names are NFC-normalised, trimmed, not blank and at most 60 characters, and compared NFC + case-folded. Over-limit lists, names or notes are refused with 422 rather than truncated. `position` is ≥ 0. Quick weekdays are de-duplicated and sorted. Explicit null is refused for the NOT NULL fields (name, child, diet, the lists, position); `notes: null` clears a note and `user_id: null` unlinks. Updates are partial (`exclude_unset`) on REST as on MCP. The Out schemas carry no validators, so rows stored before a rule existed still load, and an unknown stored diet reads as `other`.
3. **Order.** Members are listed by position, then by name with accents stripped and case folded ("Émile" before "zoe"), then newest first.
4. **References.** `add_to` and MCP updates name a member by id or by case-insensitive name. A name shared by several members (possible only in old data) is refused with "use the member id instead", never guessed. A linked `user_id` must be a user of the same household; a stale link left by a deleted user stays readable and editable.
5. **Any member may edit.** The REST routes need no `HOUSEHOLD_MANAGE` permission: members record their own diets and dislikes. MCP writes still need `household:write` and the user's confirmation. `DELETE /profile/members/{id}` returns 200 with the removed member, as Mealie's other deletes do.
6. **MCP write order.** `update_household_profile` validates every step against the state it will produce before its first write, then writes removals, updates, creates, `add_to`, then the household habits (each service writer commits on its own). Member entries accept only § 4's keys (`position` is refused); a call with nothing to do is an error; the parameters are typed `dict[str, Any]` so unknown keys get a clear message. The docstring says to send `[]` to clear a list, and that `quick_weekdays` uses 0 = Monday whatever the household's first day of the week.
7. **Household page drafts.** Each card keeps a tracked draft (`use-tracked-draft.ts`): a reload or Claude's edit flows into every field not edited on the card, edited fields keep what was typed, and Save sends only the edited fields, so it never reverts Claude's changes to the others. Fields compare in their sent form, so whitespace alone is not an edit. Undoing an edit back to where it started makes the field follow the source again, showing the current value. Text typed while a save runs is kept.
8. **Smaller UI choices.** A 422 with a validation list gives one toast: the shared `alertUnreportedError` stays quiet when the axios interceptor has already shown it, which also removes the pantry's double toast. Backspace no longer removes the last chip. The chip input explains when it is full (30) or an entry is too long (60). "Add yourself" trims the prefilled name to 60 characters.
9. **Locales.** New strings are in en-US only. CLAUDE.md forbids editing other locales (they come from Crowdin), and this overrides § 5's "en-US and fr-FR".
10. **Codegen.** `dev/code-generation/gen_ts_types.py` now renames numbered duplicate types inside unions too (`diet?: Diet2 | null` becomes `Diet | null`), which left a dangling `Diet2` before.

Deferred:

- **No re-sort after a rename.** A renamed member keeps its place on the page until the next load, while the server orders by position, then name.
- **A concurrent change can leave a partial MCP write.** Validation runs before the first write, but another request between the check and a later step can make that step fail after earlier steps committed; the tool then reports the error. A lost race inside `update_preferences` re-raises a raw `IntegrityError` that the tool does not translate. Tests for rename or relink followed by a failing step, and for the writer-failure fallback, are also still missing.
- **Removing an unsaved card discards it without asking.** Saved members get a confirmation; a new card with typed text does not.
- **Safari focus fallback.** Safari and Firefox do not focus a button on click, so after the Remove dialog closes focus goes to "Add a person" instead of the Remove button.
