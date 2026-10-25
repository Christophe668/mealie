# Household profiles slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Member profiles (diet, allergies, exclusions, dislikes, likes) and household meal habits, exposed to Claude through `get_household_context` and `update_household_profile`, editable on a Household page.

**Architecture:** Two household-scoped tables behind a `HouseholdProfileService`; REST under `/api/households/profile`; MCP context + one write tool under the existing `household:write` scope; one new frontend page. Same patterns as the pantry and feedback slices.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic 2; `mcp` SDK 2.3; Nuxt 4 + Vue 3 + Ds* primitives; pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-10-25-profiles-slice-design.md` (binding).

## Global Constraints

- Copy the feedback slice's patterns and its review lessons: scope-forcing repo `create`/`create_many` with `id.desc()` tiebreakers where ordering matters; validators on write schemas only; `NoEntryFound` → 404; validation before the first write; new `Household` relationships with `info={"filterable": False}` and no back-reference on `User`; recipe/user lookups group-wide only where needed.
- Diet values exactly `none, vegetarian, vegan, pescatarian, halal, kosher, other`; list normalisation: trim, drop empty, de-duplicate case-insensitively keeping the first spelling, ≤ 60 chars each, ≤ 30 items; weekdays 0–6 with 0 = Monday.
- No new MCP scope (`household:write` exists).
- Codegen with `PRODUCTION=false TESTING=true uv run --no-sync python dev/code-generation/main.py`, commit only this slice's generated files.
- Python via `uv run --no-sync`; pytest `-p no:xdist`, one pytest process at a time; the NAS and the main checkout's dev servers are not touched.
- UI: tokens only, one saffron purpose (allergy chips), sentence case, verbs on buttons, no middle dots, en-US + fr-FR.

## Review Focus

- A second profile linked to the same user in the same household must be refused (Task 2 `test_one_profile_per_user`).
- Names differing only by case must be refused (Task 2 `test_name_unique_case_insensitive`).
- `add_to` must append and de-duplicate, never replace (Task 4 `test_add_to_appends_without_replacing`).
- Query filters on `/api/groups/households` and `/api/groups/members` must not reach profiles or preferences (Task 1 `test_profiles_not_query_filterable`).
- The pinned Alembic head test moves to the new revision (Task 1).

---

### Task 1: Models, migration, schemas, repositories
Files: `mealie/db/models/household/household_profile.py` (both models), migration revising the feedback head `c6ecf2adb0ce`, `mealie/schema/household/household_profile.py` (`Diet`, `MemberProfileCreate/Update/Out`, `MealPreferencesUpdate/Out`, `HouseholdProfileOut`), `mealie/repos/repository_household_profile.py` (`RepositoryMemberProfiles` with `ordered()`, `by_user(user_id)`, `by_name_casefold(name)`; `RepositoryMealPreferences` with `get_for_household()`), factory properties `member_profiles` and `meal_preferences`, `Household` relationships with `info={"filterable": False}`, backup exporter untouched unless a date column is added (none), pinned head test, codegen.
Tests `tests/unit_tests/test_household_profile_models.py`: round trip with list defaults; ordering by position then name; isolation across households and groups; `test_profiles_not_query_filterable` (builder on Household + API on `/api/groups/households` and `/api/groups/members` → 400).
Commit `feat(profiles): household profile models, migration, schemas and repositories`.

### Task 2: HouseholdProfileService
File `mealie/services/claude_context/household_profile_service.py`: `HouseholdProfileService(repos, user)` with `get() -> HouseholdProfileOut`, `create_member(data)`, `update_member(id, data)` (partial), `delete_member(id)`, `add_to_member(member_ref: str, field, values)` (ref = id or case-insensitive name), `update_preferences(data)` (upsert), `normalise_list(values)`. Linking `user_id` requires a user of the same household. Errors: `NoEntryFound`, `ProfileConflict(ValueError)` for duplicate name/user.
Tests `tests/unit_tests/services_tests/test_household_profile_service.py`: normalisation; `test_name_unique_case_insensitive`; `test_one_profile_per_user`; user from another household refused; partial update keeps omitted fields; add_to append + dedupe; preferences upsert creates then updates; isolation.
Commit `feat(profiles): household profile service`.

### Task 3: REST routes
`mealie/routes/households/controller_household_profile.py` per spec § 3; `ProfileConflict` → 409, `NoEntryFound` → 404, validation → 422; register before the shopping-list router; codegen route helpers.
Tests `tests/integration_tests/user_household_tests/test_household_profile_routes.py`: full CRUD, 409s, other household 404, 401 without token, preferences upsert.
Commit `feat(profiles): rest routes for household profiles`.

### Task 4: MCP context and update tool
Modify `mealie/mcp/tools/household.py` (`preferences` per spec § 4), create `update_household_profile` in the same module (impl function + tool, scope `household:write`), docstrings per spec § 2/§ 4 (hard vs soft constraints, confirm before writing, never infer allergies).
Tests `tests/unit_tests/mcp/test_tools_household.py` (extend or create): context shape with and without profiles, `is_current_user`; create/update/remove; `test_add_to_appends_without_replacing`; validation-before-write; scope enforcement; isolation.
Commit `feat(mcp): household profiles in context and update tool`.

### Task 5: Household page
`frontend/app/lib/api/user/household-profile.ts` (client registered as `householdProfile`), `frontend/app/pages/household/profile.vue`, components under `frontend/app/components/Domain/Household/Profile/` (`ProfileMemberCard.vue`, `ProfileChipInput.vue`, `ProfileHabitsCard.vue`, `ProfileWeekdayToggles.vue`), composable `use-household-profile.ts` (sequence guard), user-menu entry "Household" in `AppShell.vue`, a link from the profile/settings page, locales.
Tests: chip input (add on Enter/comma, dedupe, remove), member card dirty/save/failure, weekday toggles respect first day of week, empty state "Add yourself" links the current user, AppShell user menu has "Household".
Screenshots 390/1280 light/dark (populated: two adults + a child with an allergy; empty) under `.superpowers/sdd/2026-10-25-profiles-slice/screenshots/`.
Commit `feat(ui): household page for member profiles and meal habits`.

### Task 6: Docs, gates, screens
`docs/fork/deploy.md` short "Household profiles" paragraph; spec "## 7. Implemented"; README line. Gates: full serial pytest, ruff format --check + check, mypy, `pnpm lint`, vitest, `task ui:build`. Screens under `screens/`. Commit `docs: household profiles slice`.
