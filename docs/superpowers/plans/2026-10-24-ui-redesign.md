# UI redesign "Mise en place" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visual layer of the Mealie fork with the "Mise en place" design: new tokens and typography, a new app shell, and rebuilt Today / Plan / Recipe / Cook / Shop / Connections screens, on top of the unchanged Mealie API.

**Architecture:** CSS custom-property tokens + Bricolage Grotesque loaded by `@nuxt/fonts`; Vuetify stays for forms, dialogs and untouched pages but its theme is re-pointed to the tokens. New primitives in `components/Design/`, a new `Layout/AppShell.vue`, and new page components under `components/Domain/{Home,Planner,Cook,Shop}/`. Pages are replaced at page level; old components stay until the cleanup task. Data access reuses the existing API clients and composables.

**Tech Stack:** Nuxt 4 (SPA), Vue 3 `<script setup lang="ts">`, Vuetify 4 (controls/dialogs only), `@nuxt/fonts`, `@vueuse/core`, vitest for composables, eslint.

**Spec:** `docs/superpowers/specs/2026-10-24-ui-redesign-design.md` (binding), with `docs/superpowers/specs/2026-10-23-mealie-fork-mcp-design.md` for everything the redesign spec does not cover.

## Global Constraints

- Tokens exactly as spec § 3: light `--stone-50 #F4F5F3`, `--stone-0 #FFFFFF`, `--stone-200 #DFE3DF`, `--stone-500 #5B655F`, `--ink #17201B`, `--saffron #F2B01E`; dark background `#121714`, surface `#1B211D`, border `#2A322D`, secondary `#9AA49E`, text `#ECEEEA`, saffron unchanged. Radii 6 / 12 / 20 px. One shadow `0 8px 24px rgb(23 32 27 / 8%)` only for floating elements.
- One typeface, "Bricolage Grotesque"; display = `font-variation-settings: "wdth" 85–92`, weight 700–800, tracking −0.02/−0.03 em; body 400 at 17 px, line-height 1.45; line length ≤ 70 ch.
- Ink text on saffron, never saffron text on white. At most one saffron element per screen.
- No all-caps labels, no eyebrows, no middle-dot meta strings, no "→" in links, no decorative gradients, no per-card hover animations; the only non-user motion is the Home board entrance; `prefers-reduced-motion` turns it off.
- Mobile-first: every screen verified at 390 px and 1280 px, light and dark, by screenshot (T3 `preview_*` tools or Playwright) — the screenshot paths go in the task report.
- i18n: every string through `$t`, keys added to `en-US.json` and `fr-FR.json`; no hard-coded English.
- Accessibility floor: visible `:focus-visible` ring (2 px ink / 2 px saffron in dark), buttons are `<button>`, images have `alt`, tap targets ≥ 44 px on mobile.
- Keep the Mealie API clients/composables; no backend changes except where a task says so.
- New code only in: `frontend/app/assets/design/**`, `frontend/app/components/Design/**`, `frontend/app/components/Layout/AppShell*.vue`, `frontend/app/components/Domain/{Home,Planner,Cook,Shop}/**`, the page files each task names, `nuxt.config.ts` (css + fonts), `plugins/theme.ts`, i18n files. Upstream components are not edited; they are replaced by new ones or wrapped.
- `task ui:lint` clean and `cd frontend && pnpm vitest run` green at the end of every task; English Conventional Commits (`feat(ui): …`).

## Review Focus

1. A recipe with no image, no times and no servings (common after URL import) must still render a tidy Tonight board, week card and recipe page — no empty grey boxes with broken `alt`. → Task 3, Task 5 tests.
2. A household with no plan at all and no shopping list must see inviting empty states on Home and Plan (never a blank page or a spinner forever). → Task 3, Task 4.
3. Very long recipe titles (80+ chars) and long ingredient lines must wrap without breaking the board, the week strip or the cook-mode step layout. → Task 3, Task 6.
4. Dark mode: every new surface uses tokens, nothing stays white; the saffron board keeps ink text. → each task's dark screenshot.
5. Keyboard: cook mode is fully drivable with ← → and Space (timer), the rail and tab bar are tabbable, and focus is visible. → Task 2, Task 6.

---

### Task 1: Tokens, typography, theme bridge

**Files:**
- Create: `frontend/app/assets/design/tokens.css`, `frontend/app/assets/design/typography.css`, `frontend/app/assets/design/reset.css`
- Modify: `frontend/nuxt.config.ts` (`css` array: add the three files before `main.css`; `fonts.families` add `{ name: "Bricolage Grotesque", provider: "google", weights: [200,300,400,500,600,700,800], styles: ["normal"] }` if the module needs it explicit), `frontend/app/plugins/theme.ts` (defaults)
- Test: `frontend/app/assets/design/tokens.test.ts` (vitest: parse `tokens.css`, assert the six light hexes and the dark set are present with the exact names)

**Interfaces:**
- Produces CSS variables on `:root` (light) and `.v-theme--dark` (dark): `--ds-bg`, `--ds-surface`, `--ds-border`, `--ds-text`, `--ds-text-2`, `--ds-accent`, `--ds-accent-text` (always ink), `--ds-radius-ctl: 6px`, `--ds-radius-card: 12px`, `--ds-radius-hero: 20px`, `--ds-shadow-float`, `--ds-font: "Bricolage Grotesque", system-ui, sans-serif`, `--ds-space: 8px`, type scale `--ds-t-1 … --ds-t-8` (0.8125 / 0.9375 / 1.0625 / 1.25 / 1.5 / 2 / 2.75 / 3.5 rem).
- Utility classes in `typography.css`: `.ds-display` (wdth 85, 800, −0.03em), `.ds-title` (wdth 92, 700, −0.02em), `.ds-body`, `.ds-muted` (`--ds-text-2`), `.ds-focus` (focus-visible ring).
- `plugins/theme.ts`: light defaults become `primary: "#F2B01E", accent: "#17201B", secondary: "#5B655F", background: "#F4F5F3", surface: "#FFFFFF", "on-primary": "#17201B"`; dark defaults `background: "#121714", surface: "#1B211D", primary: "#F2B01E", "on-primary": "#17201B"`; API-provided overrides still win. Vuetify `defaults`: `VBtn { rounded: "md", elevation: 0 }`, `VCard { elevation: 0, rounded: "lg", border: true }`, `VTextField { variant: "outlined", density: "comfortable" }` — set in `nuxt.config.ts` `vuetifyOptions.defaults`.

- [ ] **Step 1: Write the test** asserting the token names/values and that `typography.css` sets `font-family: var(--ds-font)` on `body`.
- [ ] **Step 2: Run** `cd frontend && pnpm vitest run app/assets/design` → FAIL (files missing).
- [ ] **Step 3: Implement** the three CSS files, the nuxt config changes and the theme defaults.
- [ ] **Step 4: Run** the vitest file → PASS; `task ui:lint` → PASS; start `task ui` and screenshot the existing login page at 1280 light + dark to confirm the font and palette apply.
- [ ] **Step 5: Commit** `feat(ui): design tokens, typography and theme bridge`

---

### Task 2: Design primitives and the app shell

**Files:**
- Create: `frontend/app/components/Design/DsButton.vue`, `DsCard.vue`, `DsChip.vue`, `DsSectionTitle.vue`, `DsEmpty.vue`, `DsIcon.vue` (wraps `v-icon` with `@mdi/js` paths from `$globals.icons`), `frontend/app/components/Layout/AppShell.vue`, `AppShellRail.vue`, `AppShellTabBar.vue`, `AppShellTopBar.vue`
- Modify: `frontend/app/layouts/default.vue` (render `AppShell` instead of `DefaultLayout`)
- Test: `frontend/app/components/Design/DsButton.test.ts` (renders a `<button>`, variants `primary|dark|line|ghost`, `disabled` sets `aria-disabled`), `frontend/app/components/Layout/AppShell.test.ts` (nav items present with `aria-current="page"` on the active route; tab bar hidden ≥ 1024 px via class)

**Interfaces:**
- `DsButton` props `{ variant?: "primary" | "dark" | "line" | "ghost"; size?: "md" | "lg"; to?: string; icon?: string; block?: boolean }`, default slot = label. `primary` = saffron bg + ink text.
- `DsCard` props `{ padded?: boolean; interactive?: boolean; to?: string }`, slots default/`media`.
- `DsChip` props `{ tone?: "neutral" | "accent" }`.
- `DsSectionTitle` props `{ title: string; action?: { label: string; to: string } }`.
- `DsEmpty` props `{ title: string; text?: string; action?: { label: string; to?: string; onClick?: () => void } }`.
- `AppShell` renders: rail (≥ 1024) with items `[Today → /g/:slug, Recipes → /g/:slug/recipes, Plan → /household/mealplan/planner/view, Shop → /shopping-lists]` and bottom `[Connections → /user/connections, Settings → /user/profile, user name]`; top bar with the page title slot and a search field (`⌘K` / `Ctrl K` focuses it; submit routes to `/g/:slug/recipes/finder?search=`), mobile tab bar (< 1024) with the four items plus a floating "+" opening a menu: "Add recipe from URL", "Add to plan", "Add to shopping list". Group slug via the existing `useAuthBackend()`/`useMealieAuth()` composables as `DefaultLayout.vue` does (copy the slug resolution; do not import `DefaultLayout`). Keep `TheSnackbar` and the announcements dialog mounted.
- Layout emits nothing; pages render inside `<v-main>`-equivalent `main.ds-main` with `max-width: 1200px; padding: 32px 40px` (16 px on mobile, bottom padding 96 px for the tab bar).

- [ ] **Step 1: Tests** (vitest + `@vue/test-utils`; mount with a stubbed router and i18n as the repo's existing component tests do — grep `tests` in `frontend/app/components` for the pattern).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `task ui:lint` → PASS; screenshots of Home (still old content) at 390/1280 light/dark to validate the shell. **Step 5: Commit** `feat(ui): design primitives and app shell`

---

### Task 3: Home — "Today"

**Files:**
- Create: `frontend/app/components/Domain/Home/HomeTonightBoard.vue`, `HomeSideCards.vue`, `HomeWeekStrip.vue`, `HomeRecipeShelf.vue`, `HomeDayCard.vue`, `frontend/app/composables/use-today.ts`
- Modify: `frontend/app/pages/g/[groupSlug]/index.vue` (renders the new Home; the old explorer moves to `pages/g/[groupSlug]/recipes/index.vue` if that route does not already exist — check; "Recipes" in the rail points there)
- Test: `frontend/app/composables/use-today.test.ts`

**Interfaces:**
- `useToday()` returns `{ today: Ref<Date>, tonight: Ref<ReadPlanEntry | null>, lunch: Ref<ReadPlanEntry | null>, week: Ref<Array<{ date: Date; entries: ReadPlanEntry[] }>> (7 days starting on the household's first day of week), openList: Ref<{ id, name, openCount } | null>, makeAgain: Ref<RecipeSummary[]>, recent: Ref<RecipeSummary[]>, loading, refresh }`. Data: `useUserApi().mealplans.getAll(start, end)` (one call for the week ± 0), `shopping.lists.getAll()` → most recently updated list and its unchecked count, `recipes.getAll(page 1, perPage 8, orderBy "last_made", orderDirection "asc")` for make-again (exclude never-made? no — never-made come first, that is fine, label them "Never cooked"), `recipes.getAll(perPage 8, orderBy "created_at", desc)` for recent. `tonight` = today's `dinner` entry, else the first entry of today; `lunch` = today's `lunch` entry.
- `HomeTonightBoard` props `{ entry: ReadPlanEntry | null; loading: boolean }`: saffron board with photo (recipe image via existing `useStaticRoutes().recipeImage`), label "Tonight", title (`ds-display`, clamp 3 lines), line 1 "`{total time} for {servings}`" (omit missing parts), line 2 "Last made …" (from `recipe.lastMade` if present, else omitted), buttons "Start cooking" → `/g/:slug/r/:recipeSlug/cook` and "Swap" → opens the existing `MealPlanAddRecipeDialog` for today's dinner. Empty state: same board, "Nothing planned tonight", buttons "Pick a recipe" (→ finder) and "Plan the week" (→ planner).
- `HomeWeekStrip`: 7 `HomeDayCard`s; today outlined in ink; a day with several entries shows the dinner (or first) and "+N"; empty day shows "Nothing yet" and is a link to the planner on that date. Horizontal snap scroll under 1024 px.
- Entrance motion: `HomeTonightBoard` animates `transform: translateY(12px) → 0` + opacity 0 → 1 over 320 ms once per page load; disabled under `prefers-reduced-motion`.

- [ ] **Step 1: Tests** for `useToday` with a mocked API (tonight picks dinner over lunch; week starts on `firstDayOfWeek`; `openCount` ignores checked items; empty responses give nulls not throws).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `task ui:lint`; screenshots 390/1280 light/dark with (a) a planned week, (b) an empty household, (c) a recipe without image and with an 90-char title. **Step 5: Commit** `feat(ui): today home screen`

---

### Task 4: Plan — week planner

**Files:**
- Create: `frontend/app/components/Domain/Planner/PlannerWeek.vue`, `PlannerDayColumn.vue`, `PlannerEntryCard.vue`, `PlannerDayList.vue` (mobile)
- Modify: `frontend/app/pages/household/mealplan/planner/view.vue` (replace content; keep the route and the existing `MealPlanAddRecipeDialog`, `MealPlanNoteMenu`, drag-and-drop via `vue-draggable-plus` as upstream `MealPlanDay.vue` does)
- Test: `frontend/app/components/Domain/Planner/PlannerWeek.test.ts` (groups entries by day and meal type; renders 7 columns; emits `move` with `{ entryId, date }` on drop)

**Interfaces:**
- `PlannerWeek` props `{ start: Date; entries: ReadPlanEntry[]; mealTypes: PlanEntryType[] }`, emits `move`, `add(date, type)`, `remove(entryId)`, `open(entry)`. Desktop: CSS grid 7 columns × rows for the meal types present (always at least dinner). Mobile (< 1024): `PlannerDayList` — vertical day sections, today pinned at top with a "Today" chip (the single saffron element on this screen).
- Week navigation: previous / this week / next in the top bar slot; the date is in the query `?start=YYYY-MM-DD`.
- `PlannerEntryCard`: photo thumb 56 px, title (2-line clamp), servings when ≠ recipe default, free-text entries show the title in italics-free plain weight 500 with no photo. Hover shows no animation; a kebab opens `MealPlanNoteMenu`-equivalent actions (open recipe, change servings, remove).

- [ ] **Step 1: Tests.** **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `task ui:lint`; screenshots 390/1280 light/dark with a populated and an empty week; drag an entry across days in the preview and confirm the API `PUT` fires. **Step 5: Commit** `feat(ui): week planner`

---

### Task 5: Recipe page (read view)

**Files:**
- Create: `frontend/app/components/Domain/Recipe/RecipeRead/RecipeReadPage.vue`, `RecipeReadHero.vue`, `RecipeReadIngredients.vue`, `RecipeReadSteps.vue`, `RecipeReadFacts.vue`, `RecipeReadActions.vue`
- Modify: `frontend/app/pages/g/[groupSlug]/r/[slug]/index.vue` — render `RecipeReadPage` when not in edit mode; delegate to the existing `RecipePage.vue` when the user enters edit mode (the existing `RecipePage` keeps all editors). Look at how `index.vue` and `RecipePage.vue` decide edit mode (`isEditMode`/`PageMode` in the recipe-page composable) and branch at the page level without modifying `RecipePage.vue`.
- Test: `frontend/app/components/Domain/Recipe/RecipeRead/RecipeReadIngredients.test.ts` (scaling multiplies quantities via the existing `useScaledAmount`/`parseIngredientText` helpers; ticking an ingredient toggles a `checked` class and persists in `sessionStorage` per recipe slug)

**Interfaces:**
- Layout ≥ 1024: left column 5/12 sticky (`position: sticky; top: 24px`): image (aspect 4/3, radius 20 px, placeholder = stone surface with the recipe's initial letter in `ds-display` when there is no image), `RecipeReadFacts` (prep / cook / total, servings with the existing scale control), `RecipeReadIngredients` (tickable). Right 7/12: title `ds-display` (clamp none), description, `RecipeReadSteps` (numbered 1..n — a real sequence — each step card with the step text; a "timer" chip appears when the text contains `\b(\d+)\s*(min|minutes|h|hours)\b`), notes, organizers as `DsChip`s, "Last made" line (from `recipe.lastMade`), comments section = the existing `RecipePageComments` component re-used as is.
- Mobile: single column: image, title, facts, "Start cooking" sticky bottom button (saffron, the one accent), ingredients (collapsible, open by default), steps.
- `RecipeReadActions`: Edit (→ existing edit mode), Add to plan (existing dialog), Add to shopping list (existing dialog), Share/print (existing), Delete (existing confirmation). Reuse the dialogs by importing the same components the current `RecipePage` uses; do not re-implement them.

- [ ] **Step 1: Tests.** **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `task ui:lint`; screenshots 390/1280 light/dark with a full recipe and with a bare imported recipe (no image/times/servings). Confirm edit mode still opens the upstream editor. **Step 5: Commit** `feat(ui): recipe read page`

---

### Task 6: Cook mode

**Files:**
- Create: `frontend/app/pages/g/[groupSlug]/r/[slug]/cook.vue`, `frontend/app/components/Domain/Cook/CookMode.vue`, `CookStep.vue`, `CookIngredients.vue`, `CookTimer.vue`, `CookFinish.vue`, `frontend/app/composables/use-cook-timers.ts`, `frontend/app/composables/use-wake-lock.ts`
- Test: `frontend/app/composables/use-cook-timers.test.ts` (parses "10 minutes", "1 h 30", "45 min" into seconds; multiple timers run independently; `done` fires once at zero), `frontend/app/components/Domain/Cook/CookMode.test.ts` (ArrowRight/ArrowLeft move steps; Space starts the first timer of the current step; the last step shows `CookFinish`)

**Interfaces:**
- Route `/g/:groupSlug/r/:slug/cook` uses layout `blank`; full-screen ink background (`--ds-text` on `#121714` regardless of theme — cook mode is always dark), exit button top-left, progress "Step 3 of 8" top-right.
- `CookMode` props `{ recipe: Recipe }`: current step text at `--ds-t-7` (2.75 rem; 2 rem on mobile), previous/next steps dimmed (opacity .35) above/below with a small scroll; right column (≥ 1024) `CookIngredients` listing all ingredients, the ones mentioned in the current step (word match on the food/ingredient text) highlighted in saffron; mobile: ingredients in a bottom sheet toggled by a button.
- `CookTimer`: floating pill (shadow allowed) with mm:ss, pause/reset; plays a short `AudioContext` beep and vibrates (`navigator.vibrate`) on done; several timers stack.
- `useWakeLock()`: requests `navigator.wakeLock` on mount, re-requests on `visibilitychange`, releases on unmount; no-op where unsupported.
- `CookFinish`: "How was it?" with three `DsButton`s "Loved it" / "It was fine" / "Not again" → for now calls the existing `recipes.updateLastMade(slug, today)` API (all three) and routes back to the recipe; the verdict is kept in `sessionStorage` under `pending-feedback:<slug>` for phase 2 to pick up. Button "Skip" also updates last made.

- [ ] **Step 1: Tests.** **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `task ui:lint`; screenshots 390/1280 of step 1, a running timer, and the finish screen. Keyboard check: ←/→/Space/Escape. **Step 5: Commit** `feat(ui): cook mode`

---

### Task 7: Shop — shopping list

**Files:**
- Create: `frontend/app/components/Domain/Shop/ShopList.vue`, `ShopAisle.vue`, `ShopItemRow.vue`, `ShopQuickAdd.vue`, `ShopBought.vue`
- Modify: `frontend/app/pages/shopping-lists/[id].vue` (replace the template; keep the existing `composables/shopping-list-page/**` logic — it is unit-tested upstream and must stay the single source of truth for item updates, label grouping and offline queueing), `frontend/app/pages/shopping-lists/index.vue` (list of lists as `DsCard`s with open-count and last updated)
- Test: `frontend/app/components/Domain/Shop/ShopList.test.ts` (groups by label in the list's label order, unlabelled last; checked items move to `ShopBought`; row tap toggles `checked` through the provided handler)

**Interfaces:**
- `ShopList` props `{ list: ShoppingListOut; byLabel: Array<{ label: MultiPurposeLabelSummary | null; items: ShoppingListItemOut[] }> }` (computed by the existing composable), emits `toggle(item)`, `edit(item)`, `add(text)`, `clearBought()`.
- `ShopItemRow`: 52 px tall on mobile, checkbox 24 px, display text (`item.display`), secondary line = recipe names from `item.recipeReferences` ("For Roast chicken"), quantity right-aligned; checked rows strike through and fade.
- `ShopQuickAdd`: pinned at the bottom above the tab bar on mobile, top on desktop; submits on Enter.
- `ShopBought`: collapsed section "Bought (N)" with "Clear bought items".
- "Put away" button is NOT built (phase 2).

- [ ] **Step 1: Tests.** **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `task ui:lint`; also run the upstream `pnpm vitest run app/composables/shopping-list-page` → PASS unchanged; screenshots 390/1280 light/dark. **Step 5: Commit** `feat(ui): shopping list`

---

### Task 8: Connections, consent, login — restyle; cleanup; docs

**Files:**
- Modify: `frontend/app/pages/user/connections/index.vue`, `authorize.vue`, `frontend/app/pages/login.vue` (tokens + `Ds*` primitives; content unchanged), `frontend/app/layouts/basic.vue` (tokens)
- Delete: `frontend/app/components/Layout/DefaultLayout.vue` and `LayoutParts/AppSidebar.vue`, `AppHeader.vue` only if no other layout imports them (`admin.vue` might — check; if it does, leave them)
- Modify: `README.md` fork header (one line: "UI redesigned — see the design spec"), `docs/superpowers/specs/2026-10-24-ui-redesign-design.md` (append "Implemented" notes for anything that deviated)
- Test: `task ui:lint`, `pnpm vitest run` (all), `task ui:build` (production build must pass — the Docker image uses it)

- [ ] **Step 1: Restyle the three pages and the basic layout.** **Step 2: Remove dead layout components if unreferenced.** **Step 3: `task ui:lint && pnpm vitest run && task ui:build`** → all PASS. **Step 4: Full screenshot pass**: Today, Plan, Recipe, Cook, Shop, Connections, Consent, Login at 390/1280 light/dark; save under `.superpowers/sdd/<workspace>/screens/`. **Step 5: Commit** `feat(ui): restyle auth and connections pages, remove old layout`
