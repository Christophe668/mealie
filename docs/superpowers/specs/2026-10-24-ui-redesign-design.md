# UI redesign: "Mise en place"

Date: 2026-10-24
Status: direction chosen by the builder at Christophe's request ("suggest something and implement it directly"); supersedes § 4.6 of `2026-10-23-mealie-fork-mcp-design.md`.

## 1. Brief

Subject: a household cooking companion — our recipes, this week's meals, the shopping list — with Claude as the sous-chef over MCP. Audience: Christophe (later his household), on a phone in the kitchen and on a laptop when planning. Primary job: answer **"what do we eat tonight / this week?"** in one glance, then support the two moments that follow: shopping and standing at the stove.

Constraints kept from the approved spec: Nuxt 4 + Vue 3, Mealie's API and data model, i18n (en + fr), PWA, dark mode, mobile-first, upstream mergeability (new code in our own components; upstream pages are replaced at the page level, not patched line by line).

What changes: the whole visual layer. Vuetify stays installed for forms, dialogs, menus and the admin area (untouched), but the shell, the home screen, the planner, the recipe page, cook mode, the shopping list and the Connections pages are rebuilt on our own design tokens and components. Vuetify's theme colours are re-pointed to the same tokens so untouched pages do not clash.

## 2. References and what we take from them

- **Mela** (MacStories "Best Design" 2021; "the prettiest recipe manager"): restraint, photography as the only colour, full-screen cook mode that dims every step but the current one, timers inside steps, ingredients you can tick off while cooking.
- **Crouton**: messy recipes become clean structured cards; multiple timers from the steps; a pleasant week planner on phone.
- **Paprika**: the benchmark for "it just works" — scaling, grocery lists grouped by aisle, nothing clever in the way.
- Reviews of Mealie itself praise its cook mode and calendar but call the look generic Material.

Deliberately *not* taken: swipe-to-match gimmicks, AI chrome, gradient washes, the warm-cream + serif + terracotta "editorial" look that every generated food app now wears.

## 3. Design system

### Colour (light)
| Token | Hex | Role |
|---|---|---|
| `--stone-50` | `#F4F5F3` | page background (ceramic white, cool) |
| `--stone-0` | `#FFFFFF` | raised surfaces |
| `--stone-200` | `#DFE3DF` | hairline borders, dividers |
| `--stone-500` | `#5B655F` | secondary text, icons |
| `--ink` | `#17201B` | primary text, the dark surface (cast iron with a green undertone) |
| `--saffron` | `#F2B01E` | the one accent: "Tonight", the current cook step, primary actions. Always ink text on saffron, never saffron text on white. |

Dark: background `#121714`, surface `#1B211D`, border `#2A322D`, secondary `#9AA49E`, text `#ECEEEA`, saffron unchanged. Semantic (success/warning/error) reuse Mealie's existing greens/reds but desaturated 10 %.

### Type
One family: **Bricolage Grotesque** (variable: weight 200–800, width 75–100, optical size). Display at wide width/heavy weight, body at normal width/400, labels 500. Scale (rem): 0.8125 / 0.9375 / 1.0625 (body) / 1.25 / 1.5 / 2 / 2.75 / 3.5 (hero). Line length ≤ 70 ch. No all-caps labels, no eyebrows, no middle-dot meta strings.

### Shape, depth, motion
- Radii: controls 6 px, cards 12 px, the hero board 20 px, images follow their container.
- Depth by hairline borders (`--stone-200`) and background steps, not shadows. One soft shadow (`0 8px 24px rgb(23 32 27 / 8%)`) reserved for floating things: menus, the mobile tab bar, the cook-mode timer.
- Motion: one orchestrated entrance on Home (the Tonight board rises 12 px and fades, 320 ms); everything else only answers an action (tick, open, expand). `prefers-reduced-motion` disables all of it.

### Layout
- Desktop (≥ 1024): left rail 232 px (Today, Recipes, Plan, Shop, Pantry — Pantry hidden until phase 2 — and at the bottom Connections, Settings, the user), content column max 1200 px, left-aligned, 32 px gutters. A search field in the content header, `⌘K` focuses it.
- Mobile: single column, 16 px gutters, bottom tab bar (Today, Recipes, Plan, Shop) with the floating "+" for add recipe / add to plan / add to list.
- Grid: 12 columns, 24 px gutter on desktop; 8 px base spacing unit.

### Principles
1. **Service ticket**: one glance answers tonight; density where it helps (the week strip), air where you read (steps).
2. **Saffron once**: at most one saffron element per screen — it is a pointer, not a brand wash.
3. **Photography is the colour**: everything else is stone and ink.
4. **Type carries hierarchy** through weight and width, not size explosions.
5. **Words are signposts**: sentence case, verbs on buttons ("Add to plan", "Start cooking", "Mark as bought"), empty states tell you what to do next.
6. **No meta strings**: never join facts with middle dots ("1 h 10 · 4 servings"). Facts get their own short line or a chip: "1 h 10 for 4" on one line, "Last made 6 weeks ago" on the next; card footers show one fact, the most useful.

## 4. Screens

### 4.1 Home — "Today" (`/g/:group`)
```
┌ rail ┐┌───────────────────────────────────────────────────────────────┐
│Today ││ Thursday 24 October                        [search ⌘K] [+]   │
│Recip.││ ┌──────────────────────────────────┐ ┌─────────────────────┐ │
│Plan  ││ │ TONIGHT (saffron board)          │ │ Lunch today         │ │
│Shop  ││ │ ┌photo┐ Roast chicken with…      │ │ Leftover dal, 2 p.  │ │
│      ││ │ │     │ 1 h 10 · 4 servings      │ ├─────────────────────┤ │
│      ││ │ └─────┘ [Start cooking] [Swap]   │ │ Shopping: 14 open   │ │
│      ││ └──────────────────────────────────┘ │ [Open list]         │ │
│      ││ This week                            └─────────────────────┘ │
│      ││ ┌Mon┐┌Tue┐┌Wed┐┌Thu●┐┌Fri┐┌Sat┐┌Sun┐  (7 columns, photos)   │
│Conn. ││ Make again  ─ recipes not cooked for 30+ days, horizontal    │
│You   ││ Recently added                                               │
└──────┘└───────────────────────────────────────────────────────────────┘
```
Nothing planned tonight → the board stays saffron but says "Nothing planned tonight" with "Pick a recipe" and "Ask Claude" (link to the Connections how-to while no MCP client is connected, otherwise plain copy text). Mobile: the board is full-bleed, the week is a horizontal snap strip.

### 4.2 Plan (`/household/mealplan/planner/view`)
Desktop: 7-column week grid, rows = meal types in use, cards with photo, title, servings, drag-and-drop kept from upstream. Mobile: day list, today pinned. "Add" opens the existing add dialog restyled.

### 4.3 Recipe (`/g/:group/r/:slug`)
Desktop two columns: left (5/12) sticky — photo, times, servings with the scale control, ingredients as a tickable list; right (7/12) — title set large, description, numbered steps (a real sequence) with inline timers, notes, "last made" and household feedback block (phase 2 data; renders empty until then). Mobile: single column, ingredients collapsible, floating "Start cooking".

### 4.4 Cook mode (`/g/:group/r/:slug/cook`)
Full screen, ink background. Current step 2.75 rem on the left, ingredients for that step on the right (desktop) or above (mobile); other steps dimmed; tap/arrow keys to move; timers parsed from "N minutes" in the step text, one tap to start, floating; screen kept awake (`navigator.wakeLock`); on the last step: "How was it?" with three choices that call `PATCH last-made` now and `recipe_feedback` in phase 2.

### 4.5 Shop (`/shopping-lists/:id`)
Grouped by aisle (labels), large tap targets, ticked items collapse into a "Bought" section at the bottom, quick-add field pinned, recipe-derived items show the recipe name in secondary text. "Put away" button (phase 2: moves to pantry) hidden until phase 2.

### 4.6 Connections and consent
Restyled onto the new tokens; content unchanged.

### 4.7 Everything else
Admin, settings, editors, organizers keep Vuetify but inherit the tokens through the Vuetify theme (primary = saffron, surfaces = stone, text = ink) and the global font.

## 5. Implementation notes for the plan
- Tokens live in `frontend/app/assets/design/tokens.css` (light/dark via `.v-theme--dark`) and `typography.css`; loaded in `nuxt.config.ts` `css`. Fonts through `@nuxt/fonts` (already installed): `font-family: "Bricolage Grotesque"`.
- `plugins/theme.ts` keeps its API override but its defaults become the tokens.
- New components under `frontend/app/components/Design/` (primitives: `DsButton`, `DsCard`, `DsChip`, `DsSectionTitle`, `DsEmpty`) and `frontend/app/components/Domain/{Home,Planner,Cook,Shop}/`. Pages are replaced, not patched; the old components stay in the tree until the final cleanup task.
- Shell: `components/Layout/AppShell.vue` replaces `DefaultLayout.vue` for the `default` layout; `basic`/`admin` layouts get the tokens only.
- Each screen task ends with a screenshot review at 390 px and 1280 px in light and dark.
