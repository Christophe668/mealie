# Mealie fork: native MCP for Claude and a modernised UI

Date: 2026-10-23
Status: approved 2026-10-23

## 1. Intent

Christophe wants his own version of Mealie, self-hosted in Docker, that
Claude can drive from the claude.ai app (phone or web) at any time. The
central use case: **asking Claude what to eat** today, tonight or this week,
then letting it fill in the meal plan and the shopping list once the
proposal is approved.

Guiding principle: **Mealie holds the data, Claude does the reasoning.** We
do not add "AI suggestions" inside Mealie. We give Claude precise tools to
read and write Mealie, plus enough context (household, history, pantry,
feedback) for its proposals to be good.

Second track: a more modern interface, organised around the moments of the
day, without rewriting the frontend.

## 2. Goals, non-goals, anti-goals

**Goals**

- A working claude.ai remote connector: HTTPS, OAuth, MCP Streamable HTTP,
  served by the Mealie container itself.
- MCP tools covering: search, propose, plan, shop, import/create recipes,
  read and write household context.
- A "memory" that improves proposals over time: household profiles, pantry,
  post-meal feedback, leftovers.
- A modernised interface on the key screens, plus new screens for the added
  features.
- Staying able to pull upstream Mealie updates.

**Non-goals**

- No rewrite of the backend or the frontend. We add and retouch.
- No native mobile app: the claude.ai app and the Mealie PWA are enough.
- No recommendation engine inside Mealie: that is Claude's job.
- No direct integration with third-party shopping apps inside Mealie (see
  § 6.4: Claude does that itself through its other connectors).

**Anti-goals** (what would make this project a failure even if it "works")

- An MCP endpoint reachable without authentication, or with a hard-coded
  shared token, on an internet-exposed server.
- A fork so divergent that `git merge upstream/mealie-next` becomes
  impractical after three months.
- A "modern" UI that breaks existing Mealie features (URL import,
  multi-household, i18n, PWA).

## 3. Constraints and existing state

Base: `mealie-recipes/mealie` v3.29.0 (commit `8017e04`, 2026-10-23).

- Backend FastAPI 0.146, Python 3.14, SQLAlchemy 2.1, Alembic, Pydantic 2,
  Authlib 1.9 already present (used as an OIDC client).
- Frontend Nuxt 4 (SPA, `ssr: false`), Vue 3, Vuetify 4, i18n, PWA. Theme
  built at runtime from `/api/app/about/theme`
  (`frontend/app/plugins/theme.ts`, colours in
  `mealie/core/settings/themes.py`).
- Model: `Group` > `Household` > `User`. All repositories are automatically
  scoped by group/household (`AllRepositories(session, group_id,
  household_id)`).
- Existing tokens: HS256 JWTs signed with `settings.SECRET`. Long-lived
  tokens (`long_live_tokens`) carry `{"long_token": true, "id", "name",
  "integration_id"}` and are validated by a DB lookup
  (`mealie/core/dependencies/dependencies.py`).
- No MCP code and no OAuth server in the repo.
- `mealie/app.py` mounts the SPA as a catch-all after the API routers: any
  new entry point (`/mcp`, `/.well-known/*`, OAuth routes) must be
  registered **before** `spa.mount_spa(app)`.
- Docker: single multi-stage image (frontend generated, then embedded in
  the Python package); `docker/entry.sh` handles PUID/PGID and `*_FILE`
  secrets.

## 4. Chosen architecture

```
claude.ai (web / mobile)
   │  HTTPS
   ▼
TLS reverse proxy (Caddy, Traefik, Cloudflare Tunnel… hosting's choice)
   │
   ▼
Mealie container (fork)
   ├── /api/**            existing Mealie API
   ├── /authorize, /token, /register, /revoke   OAuth 2.1 server (new)
   ├── /.well-known/**    OAuth metadata (new)
   ├── /mcp               MCP Streamable HTTP server (new)
   └── /**                Nuxt SPA (UI, retouched)
   │
   ▼
Postgres (separate container)
```

### 4.1 Code organisation (to stay mergeable)

Everything new lives in our own folders; upstream files are only touched to
wire those folders in.

- `mealie/mcp/`: MCP server, tools, input/output schemas, OAuth provider,
  tests.
- `mealie/services/claude_context/`: "household memory" services
  (profiles, pantry, feedback, leftovers) used by both the REST API and
  MCP.
- `mealie/routes/claude/`: REST routes for the new screens (pantry,
  feedback, MCP connections).
- `frontend/app/components/Domain/{Home,Pantry,Feedback,Connections}/` and
  associated pages.
- Git: remote `upstream` = Mealie, remote `origin` = Christophe's GitHub
  fork. Working branch `main`. Upstream updates come in via `git merge
  upstream/mealie-next`; we aim for conflicts limited to `app.py`,
  `routes/__init__.py`, `pyproject.toml`, `Dockerfile`, and the layout
  components.

### 4.2 OAuth 2.1 server (new, inside Mealie)

Why: claude.ai remote connectors authenticate with OAuth. Mealie can only
act as an OIDC client, so it needs the authorization-server role added.
Decision: implement it inside Mealie rather than adding a third-party
container, so the "token ↔ user ↔ household" link stays native and visible
in the settings.

Update after recon (my call): the Python `mcp` SDK v2 already ships the
authorization-server routes and the Bearer middleware; we implement its
`OAuthAuthorizationServerProvider` protocol backed by the Mealie database
rather than rewriting OAuth with Authlib. Consequence: the paths are the
SDK's (`/authorize`, `/token`, `/register`, `/revoke` at the root).

What it provides:

- `GET /.well-known/oauth-authorization-server` and
  `GET /.well-known/oauth-protected-resource/mcp` (metadata).
- `POST /register`: dynamic client registration (RFC 7591), required by
  claude.ai. Registered clients are stored in the DB with their
  `redirect_uris`.
- `GET /authorize`: redirects to a consent page in the SPA. The user logs
  in with their usual Mealie account (including upstream OIDC/LDAP, since
  the Mealie session is reused), sees the client name and scopes, approves
  or denies.
- `POST /token`: code → tokens exchange, PKCE mandatory (S256); refresh
  with refresh-token rotation.
- `POST /revoke`.
- Access tokens: JWTs signed with `settings.SECRET`, claims
  `{"sub": user_id, "mcp": true, "cid": client_id, "scope": ...}`, short
  lifetime (1 h); opaque refresh tokens, stored hashed, 90-day lifetime,
  revocable.
- Scopes: `recipes:read`, `recipes:write`, `mealplan:write`,
  `shopping:write`, `household:write`. Claude asks for all by default; the
  user sees what they grant.
- A "Connections" page in user settings: list of authorised clients, last
  used date, Revoke button.
- Token scope (my call): a token carrying `mcp: true` is accepted **only**
  on `/mcp`. `get_current_user` explicitly rejects it on `/api/**`, and the
  MCP server has its own dependency that validates it and builds the same
  user/group/household context as a Mealie controller. Scopes are checked
  per tool (each tool declares its required scope); an out-of-scope call
  returns an explicit MCP error.

Deliberate limits: a single authorization server (no federation), no
`client_credentials` flow, no user-less tokens.

### 4.3 MCP server

- Library: official Python `mcp` SDK, Streamable HTTP transport, mounted in
  the existing FastAPI app under `/mcp`. No separate process.
- Every MCP request carries an OAuth Bearer; the server builds a
  `(user, group, household, repos)` context identical to a Mealie
  controller's. Without a valid token: 401 with a `WWW-Authenticate`
  header pointing to the metadata, as the MCP spec requires.
- Tools call **services**, never HTTP controllers. Where logic currently
  lives in a controller (e.g. random meal-plan draw in
  `controller_mealplan.py`), extract it into a service used by both first.
- Responses are compact and model-oriented: recipe summaries (name, slug,
  times, tags, rating, last made, servings) rather than the full object;
  the full object is available on request.
- Every write returns what was created/modified with its id and, where
  relevant, the URL of the matching Mealie page.

### 4.4 MCP tools

`snake_case` names, descriptions written for Claude (when to use the tool,
what it returns, pitfalls).

**Context and decision**

| Tool | Role |
|---|---|
| `get_household_context` | One call: household members, allergies/exclusions, preferences, default servings, "quick" days, timezone, units. |
| `search_recipes` | Search by text, tags, categories, tools, ingredients, max time, min rating, "not made for N days", in season (current month). Pagination, sorting including `random`. Built on `page_all` and the existing filter DSL. |
| `get_recipe` | Full recipe by slug or id. |
| `get_recent_meals` | History of planned/made meals over N days, to avoid repetition. |
| `get_mealplan` | Plan between two dates. |
| `get_pantry` | Pantry contents, soonest-expiring first. |
| `get_recipe_feedback` | Household feedback on a recipe, or the last N entries. |
| `get_today_brief` | Today's and tomorrow's meals, items to take out/defrost, pantry items about to expire, open shopping list. Powers the "morning brief". |

**Action**

| Tool | Role |
|---|---|
| `add_mealplan_entries` | Adds one or more entries (date, meal type, recipe or free text, servings). `leftovers_of` option to mark a leftover of another entry. |
| `remove_mealplan_entry` / `move_mealplan_entry` | Corrections. |
| `create_shopping_list_from_mealplan` | Creates (or tops up) a list from a period's entries, **deducting what is already in the pantry**; grouped by aisle (Mealie labels). Returns the list and what was excluded thanks to the pantry. Deduction **by presence** (my call): if the food is in the pantry, it is not bought, with no quantity maths (Mealie has no unit conversion). Deducted items are returned to Claude, which can add them back if the user asks. |
| `add_shopping_items` / `check_shopping_items` | Manual additions and ticking. |
| `get_shopping_list` | Read a list (for Claude to export elsewhere). |
| `update_pantry` | Adds, removes or adjusts pantry items (after shopping, after a meal). |
| `record_recipe_feedback` | Records feedback: verdict (`loved` / `ok` / `never_again`), perceived effort, free note, by whom, for which date. Updates rating and `last_made`. |
| `import_recipe_from_url` | Scraping via the existing service (recipe sites, and videos via yt-dlp where supported). |
| `create_recipe` | Structured creation. This is the "photo" path: Claude reads the image itself in the conversation and calls this tool with the extracted data. Mealie makes no AI call. No image transfer over MCP (my call): optional `image_url` parameter if Claude has a public URL, otherwise the recipe is created without a photo and the response includes the Mealie page link to add one. |
| `update_household_preferences` | Updates household profiles/preferences. |

**MCP resources and prompts**

- Resource `mealie://household/context` (same content as
  `get_household_context`, for clients that prefer resources).
- Prompt `plan_week`: template chaining context → history → search →
  proposal → approval → write, with household constraints. Prompt
  `tonight` for the short version.

### 4.5 Household memory (new models)

Everything scoped by household (`household_id`), with Alembic migration.

- `household_profiles`: per member (linked to a `User` or a plain name for
  a child), allergies, exclusions, dislikes, preferences, servings. And at
  household level: default servings, "quick" days, weekday max time,
  favourite cuisines.
- `pantry_items`: food (link to `IngredientFood` when possible), quantity
  and unit **optional and informational**, location
  (fridge/freezer/cupboard), expiry date, source (shopping, manual,
  leftover).
- `recipe_feedback`: recipe, member, date, verdict, effort (1-3), free
  note. Recording also creates a Mealie timeline event
  (`event_type=comment`) so it stays visible in the existing UI.
- Leftovers: `leftover_of_id` column on `group_meal_plans` + a "recipe
  servings − household servings" rule exposed by the service, used by
  Claude to propose the leftover for the next day.
- "In season": static `seasonal_foods` table (food → months), Western
  Europe by default, editable.

### 4.6 Modernised UI

Approach: keep Vuetify 4 and the Nuxt structure, introduce a real token set
(colours, radii, spacing, typography) through the existing theme mechanism,
and rework screen by screen. Visual direction and typography to be defined
by the builder at implementation time (`frontend-design` skill), with a
preview to approve before generalising.

Screens to rework:

1. **Home** (replaces the explorer as the entry page): three blocks
   "Today / Tonight / This week", quick access to the pantry and the open
   shopping list, then recipe exploration below. The primary button opens
   the planner.
2. **Planner**: more visual week view (cards with image, meal type,
   servings, "leftover" badge), existing drag-and-drop kept.
3. **Recipe page**: airier hierarchy, ingredients and steps side by side on
   large screens, "last made / household feedback" block.
4. **Cook mode**: full screen, step by step, large type, screen kept awake,
   "how was it?" feedback at the end (feeds `recipe_feedback`).
5. **Shopping list**: by aisle, plan-derived items distinguished from manual
   additions, "I've put the shopping away" button that moves ticked items
   into the pantry.
6. **New screens**: Pantry; Household profiles; Connections (OAuth
   clients); OAuth consent page.

Constraints: i18n (fr + en at minimum, reusing the existing system),
mobile-first responsive, PWA kept, dark mode.

### 4.7 Docker and exposure

- `docker-compose.yml` at the fork root: `mealie` service (image built from
  the fork) + `postgres`, persistent volumes, documented environment
  variables (`BASE_URL` mandatory: it feeds the OAuth metadata).
- Image published to GHCR by a fork GitHub Action on every tag.
- TLS left to the hosting's reverse proxy. The fork docs describe two
  options: Caddy (domain + open port) and Cloudflare Tunnel (no open port).
  The builder provides an example of each.
- The existing `healthcheck` is kept; a `/mcp` check is added.

### 4.8 Security

- No `/mcp` or `/token` route without a valid token; PKCE mandatory;
  `redirect_uri` strictly equal to the registered one.
- Simple rate limiting on the OAuth routes including `/register`.
- MCP call log (tool, user, duration, success) at `INFO` level, with no
  recipe content.
- MCP tokens never grant access to admin routes.
- Tests: full OAuth flow, refusal without PKCE, effective revocation,
  household isolation (a household A token sees nothing of household B).

## 5. Phases

1. **Foundation**: GitHub fork, remotes, image CI, compose, OAuth, MCP with
   `get_household_context` (minimal version), `search_recipes`,
   `get_recipe`, `get_recent_meals`, `get_mealplan`,
   `add_mealplan_entries`, `create_shopping_list_from_mealplan`,
   `get_shopping_list`. Connections + consent pages. Connector tested from
   claude.ai mobile.
2. **Household memory**: profiles, pantry, feedback, leftovers, season, and
   the associated tools; pantry deduction in shopping; `get_today_brief`;
   `plan_week` / `tonight` prompts.
3. **UI**: theme tokens, home, planner, recipe page, cook mode, shopping
   list, pantry and profile screens.
4. **Extras**: `import_recipe_from_url`, `create_recipe` (photo / link
   path), "morning brief" guide with a Claude scheduled task, "share with
   another household member" guide, shopping export guide via Claude's
   connectors.

Each phase ends with a real test from the claude.ai app.

## 6. Decisions made and what is left to the builder

### 6.1 Christophe's decisions

- Fork Mealie (not an app from scratch).
- Docker hosting.
- Reachable at all times from claude.ai, hence a remote connector.
- Scope: everything listed here (core + household memory + UI + extras), in
  phase order.
- **A single Claude user for now** (Christophe). Consequences: the author
  of feedback and plan entries is the token's user;
  `record_recipe_feedback` accepts a free "for whom" field (household
  member) but the author stays the token; the Connections page is per user,
  which will also do if other members connect later. The "share with
  another member" guide moves to the end of phase 4, with no extra model
  work.

### 6.2 Decisions made by me (challenge if needed)

- OAuth 2.1 implemented inside Mealie via the MCP SDK's authorization
  server protocol, rather than a separate auth container.
- Official Python `mcp` SDK, Streamable HTTP, mounted in FastAPI.
- No AI call on the Mealie side for the new features; the upstream OpenAI
  service stays as is for its existing uses.
- Vuetify kept; no migration to another UI library.
- Feedback stored in a dedicated table rather than only as a timeline
  comment.
- Shopping export and morning brief: done by Claude (its connectors and
  scheduled tasks), not by Mealie.

### 6.3 Left to the builder

- Precise visual direction (palette, font, radii), to be proposed as a
  preview before generalising.
- Exact input/output schemas of the MCP tools.
- Exact table structures and migrations.
- Choice between Caddy and Cloudflare Tunnel for the main docs example
  (both must be documented).
- Frontend test strategy for the new screens.

### 6.4 Open questions

- Existing Mealie instance? If yes, migrate via Mealie's standard
  backup/restore in phase 1. If its ingredients are not linked to foods
  ("parsed"), phase 2 adds a "parse all ingredients" action (existing NLP
  parser, no AI) before enabling pantry deduction. To confirm; otherwise we
  start from an empty instance.
- Check that the claude.ai account allows custom connectors (Settings →
  Connectors → Add custom connector), web and mobile. Prerequisite for
  phase 1.
- Where will the container be hosted (NAS, VPS, home machine) and does a
  domain name already exist? Does not block phase 1 (local testing through
  a tunnel works), but determines which deployment example to polish.
