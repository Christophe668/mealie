# Phase 1 "Foundation": fork, OAuth, MCP, Docker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Mealie fork whose container serves an MCP server on `/mcp`, protected by a built-in OAuth 2.1 server, with the basic search / meal-plan / shopping tools, addable as a custom connector in claude.ai.

**Architecture:** The Python `mcp` SDK (v2) provides the Streamable HTTP transport, the Bearer middleware and the authorization-server routes (`/authorize`, `/token`, `/register`, `/revoke`, `/.well-known/*`). We give it an `OAuthAuthorizationServerProvider` backed by the Mealie database (`mealie/mcp/oauth/`), a consent page in the SPA, and MCP tools (`mealie/mcp/tools/`) that call Mealie repos/services with the usual group/household scoping. MCP tokens are JWTs signed with `settings.SECRET` carrying `mcp: true`; `get_current_user` rejects them on `/api/**`.

**Tech Stack:** FastAPI 0.146 / Python 3.14 / SQLAlchemy 2.1 / Alembic / Pydantic 2 / PyJWT; `mcp==2.3.0`; Nuxt 4 + Vuetify 4; Docker Compose + GHCR.

**Spec:** `docs/superpowers/specs/2026-10-23-mealie-fork-mcp-design.md`

## Global Constraints

- Python `>=3.14,<3.15`; dependencies pinned with `==` in `pyproject.toml` (Mealie convention). Add `mcp==2.3.0`.
- New backend code only in `mealie/mcp/**` and `mealie/routes/users/mcp_connections.py`; upstream files touched: `mealie/app.py`, `mealie/core/dependencies/dependencies.py`, `mealie/routes/users/__init__.py`, `mealie/db/models/__init__.py` (model import), `pyproject.toml`, `tests/utils/api_routes/__init__.py` (generated).
- A token carrying the `mcp` claim is **never** accepted on `/api/**` nor on admin routes.
- PKCE S256 mandatory; `redirect_uri` strictly equal to one of the registered `redirect_uris` (SDK default behaviour, do not relax).
- Lifetimes: access token 3600 s; refresh token 90 days with rotation; authorization code 600 s; pending consent request 600 s.
- Exact scopes: `recipes:read`, `recipes:write`, `mealplan:write`, `shopping:write`, `household:write`. A client that requests none gets all five.
- MCP tool names in `snake_case`, exactly as listed in spec § 4.4.
- All MCP/OAuth routes are registered **before** `spa.mount_spa(app)` and also in `TESTING` mode.
- `BASE_URL` is the OAuth issuer and the base of `resource_server_url` (`{BASE_URL}/mcp`).
- After any Pydantic schema or route change: `task dev:generate` (regenerates `tests/utils/api_routes` and the TS types).
- Verification commands: `task py:test -- <args>`, `task py:lint`, `task py:mypy`, `task ui:lint`.
- Frequent commits, English Conventional Commits messages (`feat(mcp): ...`).

## Review Focus

1. A regular Mealie session token (no `mcp` claim) sent to `POST /mcp` must be refused (401), otherwise any browser session becomes an MCP client. → test in Task 8.
2. An MCP token of a household A user must see no recipe/plan/list of household B in the same group, and nothing from another group. → test in Task 10.
3. An already-used refresh token (rotation) must be refused and revoke the whole grant (replay detection). → test in Task 6.
4. Revoking a connection from the Connections page must make a still-valid access token unusable (not just the refresh token). → test in Task 7.
5. `add_mealplan_entries` with an unknown `recipe_slug` or a malformed date must return a readable MCP error, not a 500 nor a partial batch (batch atomicity). → test in Task 11.

---

### Task 1: GitHub fork, remotes, working branch

**Files:**
- Modify: `.git/config` (via commands), `README.md` (fork header)
- Create: commit of the specs under `docs/superpowers/`

- [ ] **Step 1: Rename the remote and create the fork**

```bash
cd /Users/christophe/Documents/Projects/Personal/mealie
git remote rename origin upstream
git fetch --unshallow upstream
gh repo fork mealie-recipes/mealie --remote --remote-name origin --fork-name mealie
git checkout -b main
```

- [ ] **Step 2: Verify**

Run: `git remote -v && git branch --show-current`
Expected: `origin` → `github.com/Christophe668/mealie`, `upstream` → `mealie-recipes/mealie`, branch `main`.

- [ ] **Step 3: Add a 6-line block at the top of `README.md`**: "Fork of Mealie with a native MCP server for Claude", links to the spec and plan, sentence "Upstream: mealie-recipes/mealie, merged from `upstream/mealie-next`".

- [ ] **Step 4: Commit and push**

```bash
git add README.md docs/superpowers
git commit -m "docs: add fork design spec and phase 1 plan"
git push -u origin main
```

---

### Task 2: `mcp` dependency and OAuth models + migration

**Files:**
- Modify: `pyproject.toml` (dependencies), `uv.lock` (via `uv lock`)
- Create: `mealie/db/models/mcp/__init__.py`, `mealie/db/models/mcp/oauth.py`
- Modify: `mealie/db/models/__init__.py` (add `from .mcp import *`)
- Create: `mealie/alembic/versions/2026-10-23-00.00.00_<rev>_add_mcp_oauth_tables.py` (via `task py:migrate -- "add mcp oauth tables"`)
- Test: `tests/unit_tests/mcp/__init__.py`, `tests/unit_tests/mcp/test_oauth_models.py`

**Interfaces:**
- Produces (all `SqlAlchemyBase, BaseMixins`, auto int `id` unless stated):
  - `McpOAuthClient` table `mcp_oauth_clients`: `client_id: str` (unique, index), `client_secret_hash: str | None`, `client_name: str | None`, `redirect_uris: list[str]` (JSON), `metadata_json: dict` (JSON, the full `OAuthClientInformationFull.model_dump()`), `created_at`.
  - `McpOAuthPendingAuth` table `mcp_oauth_pending_auths`: `request_id: str` (unique, index, 32 urlsafe bytes), `client_id: str`, `params_json: dict` (`AuthorizationParams.model_dump(mode="json")`), `expires_at: datetime`.
  - `McpOAuthCode` table `mcp_oauth_codes`: `code: str` (unique, index), `client_id`, `user_id: GUID` FK `users.id`, `scopes: list[str]` (JSON), `code_challenge: str`, `redirect_uri: str`, `redirect_uri_provided_explicitly: bool`, `resource: str | None`, `expires_at`.
  - `McpOAuthGrant` table `mcp_oauth_grants`: `grant_id: str` (unique, index), `user_id: GUID` FK, `client_id`, `scopes` (JSON), `last_used_at: datetime | None`, `revoked_at: datetime | None`.
  - `McpOAuthRefreshToken` table `mcp_oauth_refresh_tokens`: `token_hash: str` (unique, index), `grant_id: str` (index), `client_id`, `scopes` (JSON), `resource: str | None`, `expires_at`, `used_at: datetime | None`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` → `dependencies`, add `"mcp==2.3.0",`. Run: `uv lock && uv sync`. Expected: `uv run python -c "import mcp.server.mcpserver, mcp.server.auth.routes; print('ok')"` → `ok`.

- [ ] **Step 2: Write the test**

```python
# tests/unit_tests/mcp/test_oauth_models.py
from mealie.db.models.mcp.oauth import McpOAuthClient, McpOAuthGrant

def test_oauth_client_roundtrip(session):
    session.add(McpOAuthClient(client_id="c1", client_name="Claude", redirect_uris=["https://claude.ai/api/mcp/auth_callback"], metadata_json={"client_id": "c1"}))
    session.commit()
    row = session.query(McpOAuthClient).filter_by(client_id="c1").one()
    assert row.redirect_uris == ["https://claude.ai/api/mcp/auth_callback"]

def test_grant_defaults(session, unique_user):
    g = McpOAuthGrant(grant_id="g1", user_id=unique_user.user_id, client_id="c1", scopes=["recipes:read"])
    session.add(g); session.commit()
    assert g.revoked_at is None and g.last_used_at is None
```

- [ ] **Step 3: Run** `task py:test -- tests/unit_tests/mcp -v` → FAIL (ImportError).

- [ ] **Step 4: Create the models** in `mealie/db/models/mcp/oauth.py` with the columns from the Interfaces block (JSON via `sqlalchemy.JSON`, GUID via `mealie.db.models._model_utils.guid.GUID`, datetimes via `NaiveDateTime`). Export from `mealie/db/models/mcp/__init__.py` and import in `mealie/db/models/__init__.py`.

- [ ] **Step 5: Generate the migration**: `task py:migrate -- "add mcp oauth tables"`. Open the generated file, check that only the 5 tables are created (no drops elsewhere).

- [ ] **Step 6: Run** `task py:test -- tests/unit_tests/mcp -v` → PASS. Then `task py:test -- tests/unit_tests/test_alembic* -v` (upstream migrations/models consistency test, if present) → PASS.

- [ ] **Step 7: Commit** `feat(mcp): add mcp dependency and oauth tables`

---

### Task 3: MCP tokens (issue, decode, hash)

**Files:**
- Create: `mealie/mcp/__init__.py`, `mealie/mcp/oauth/__init__.py`, `mealie/mcp/oauth/tokens.py`, `mealie/mcp/scopes.py`
- Test: `tests/unit_tests/mcp/test_tokens.py`

**Interfaces:**
- `mealie/mcp/scopes.py`: `ALL_SCOPES: tuple[str, ...] = ("recipes:read", "recipes:write", "mealplan:write", "shopping:write", "household:write")`.
- `mealie/mcp/oauth/tokens.py`:
  - `ACCESS_TOKEN_TTL = timedelta(hours=1)`, `REFRESH_TOKEN_TTL = timedelta(days=90)`, `AUTH_CODE_TTL = timedelta(minutes=10)`, `PENDING_AUTH_TTL = timedelta(minutes=10)`.
  - `class McpTokenClaims(BaseModel)`: `sub: str`, `cid: str`, `gid: str`, `scope: list[str]`, `aud: str | None`, `exp: int`, `iat: int`, `jti: str`.
  - `issue_access_token(*, user_id: str, client_id: str, grant_id: str, scopes: list[str], resource: str | None) -> tuple[str, int]`: HS256 JWT signed with `settings.SECRET` (same `ALGORITHM` as `mealie.core.security.tokens`), claims `mcp: True`, `iss: "mealie"`, `scope` as a space-separated string in the JWT (list in `McpTokenClaims`); returns `(token, expires_at_epoch)`.
  - `decode_access_token(token: str) -> McpTokenClaims | None`: `None` if invalid signature, expired, or `mcp` claim absent.
  - `new_opaque_token() -> str` (`secrets.token_urlsafe(32)`), `hash_token(raw: str) -> str` (sha256 hex).

- [ ] **Step 1: Tests**

```python
def test_issue_and_decode_roundtrip():
    tok, exp = issue_access_token(user_id="u", client_id="c", grant_id="g", scopes=["recipes:read"], resource="http://x/mcp")
    claims = decode_access_token(tok)
    assert claims and claims.sub == "u" and claims.scope == ["recipes:read"] and claims.aud == "http://x/mcp" and claims.exp == exp

def test_decode_rejects_session_token():
    tok, _ = create_access_token({"sub": "u"})   # regular Mealie token
    assert decode_access_token(tok) is None

def test_decode_rejects_expired(monkeypatch):
    monkeypatch.setattr(tokens, "ACCESS_TOKEN_TTL", timedelta(seconds=-1))
    assert decode_access_token(issue_access_token(...)[0]) is None

def test_hash_token_is_stable_and_not_identity():
    raw = new_opaque_token(); assert hash_token(raw) == hash_token(raw) and hash_token(raw) != raw
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat(mcp): token issuance and decoding`

---

### Task 4: `get_current_user` rejects MCP tokens

**Files:**
- Modify: `mealie/core/dependencies/dependencies.py:102-140` (`get_current_user`) and `is_logged_in`
- Test: `tests/integration_tests/mcp/__init__.py`, `tests/integration_tests/mcp/test_api_rejects_mcp_tokens.py`

- [ ] **Step 1: Test**

```python
def test_mcp_token_rejected_on_api(api_client, unique_user):
    tok, _ = issue_access_token(user_id=str(unique_user.user_id), client_id="c", grant_id="g", scopes=list(ALL_SCOPES), resource=None)
    r = api_client.get(api_routes.users_self, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run** → FAIL (200). **Step 3:** right after `jwt.decode`, `if payload.get("mcp"): raise credentials_exception` (in `get_current_user`) and `return False` (in `is_logged_in`). **Step 4: Run** → PASS, then `task py:test -- tests/unit_tests/test_security* tests/integration_tests/user_tests -q` → PASS. **Step 5: Commit** `feat(mcp): reject mcp tokens on the regular api`

---

### Task 5: OAuth store (database access)

**Files:**
- Create: `mealie/mcp/oauth/store.py`
- Test: `tests/unit_tests/mcp/test_oauth_store.py`

**Interfaces:** `class OAuthStore:` `__init__(self, session: Session)`; synchronous methods:
- `get_client(client_id) -> OAuthClientInformationFull | None`; `save_client(info: OAuthClientInformationFull) -> None`
- `create_pending(client_id, params: AuthorizationParams) -> str` (request_id); `pop_pending(request_id) -> tuple[str, AuthorizationParams] | None` (deletes; `None` if absent/expired); `peek_pending(request_id) -> tuple[str, AuthorizationParams] | None`
- `create_code(*, client_id, user_id, params: AuthorizationParams) -> str`; `pop_code(code) -> McpOAuthCode | None` (deletes; `None` if expired)
- `create_grant(*, user_id, client_id, scopes) -> McpOAuthGrant`; `get_grant(grant_id) -> McpOAuthGrant | None` (ignores rows with `revoked_at` set); `list_grants(user_id) -> list[McpOAuthGrant]`; `revoke_grant(grant_id, user_id) -> bool` (sets `revoked_at`, deletes refresh tokens); `touch_grant(grant_id) -> None`
- `create_refresh_token(*, grant_id, client_id, scopes, resource) -> str` (raw); `consume_refresh_token(raw) -> McpOAuthRefreshToken | None`: `None` if unknown/expired; if `used_at` already set → **revokes the grant** and returns `None`; otherwise sets `used_at`.
- `purge_expired() -> None`

- [ ] **Step 1: Tests** (fixtures `session`, `unique_user`): `test_client_roundtrip`, `test_pending_pop_is_single_use`, `test_pending_expired_returns_none` (monkeypatch `PENDING_AUTH_TTL` negative), `test_code_pop_single_use`, `test_refresh_reuse_revokes_grant` (consume the same raw twice → 2nd call `None` and `get_grant` → `None`), `test_revoke_grant_only_by_owner` (other `user_id` → `False`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat(mcp): oauth persistence store`

---

### Task 6: `MealieOAuthProvider` (SDK protocol)

**Files:**
- Create: `mealie/mcp/oauth/provider.py`
- Test: `tests/unit_tests/mcp/test_oauth_provider.py`

**Interfaces:**
- `class MealieOAuthProvider(OAuthAuthorizationServerProvider[McpAuthCode, RefreshToken, AccessToken])` (SDK types from `mcp.server.auth.provider`). `McpAuthCode(AuthorizationCode)` = the SDK `AuthorizationCode` model + field `user_id: str`.
  - `__init__(self, session_factory: Callable[[], ContextManager[Session]] = session_context)`.
  - `authorize(client, params) -> str`: `store.create_pending(...)` then returns `f"{settings.BASE_URL}/user/connections/authorize?request_id={rid}"`. If `params.scopes` is empty → replace with `list(ALL_SCOPES)` before storing.
  - `complete_authorization(request_id: str, user_id: str, approve: bool) -> str` (method **outside the protocol**, called by the consent route): `pop_pending`; if `approve` creates a code and returns `construct_redirect_uri(redirect_uri, code=..., state=...)`; otherwise `construct_redirect_uri(redirect_uri, error="access_denied", state=...)`. Raises `KeyError` if request_id unknown/expired.
  - `exchange_authorization_code(client, code)`: creates a grant, issues access token (Task 3) + refresh token (Task 5); `OAuthToken(access_token, token_type="Bearer", expires_in=3600, scope=" ".join(scopes), refresh_token=raw)`.
  - `exchange_refresh_token(client, refresh_token, scopes)`: requested scopes ⊆ grant scopes else `TokenError("invalid_scope")`; consumes the old one, issues new access + refresh.
  - `load_access_token(token)`: `decode_access_token` → `None` if invalid; checks `store.get_grant(claims.gid)` not revoked, `touch_grant`; returns `AccessToken(token=token, client_id=cid, scopes=scope, expires_at=exp, resource=aud, subject=sub)`.
  - `revoke_token(token)`: if `AccessToken` → revokes grant `gid`; if `RefreshToken` → consumes + revokes the grant.
  - `get_client`, `register_client`, `load_authorization_code`, `load_refresh_token`: delegate to the store. `load_refresh_token` does not consume (read-only); consumption happens in `exchange_refresh_token`.
- `get_provider() -> MealieOAuthProvider` (module-level `lru_cache` singleton).
- Check the exact protocol signatures first with `uv run python -c "import inspect, mcp.server.auth.provider as p; print(inspect.getsource(p.OAuthAuthorizationServerProvider))"`.

- [ ] **Step 1: Tests** (async, `pytest.mark.anyio` or `asyncio.run`): `test_authorize_returns_consent_url_with_request_id`, `test_authorize_defaults_to_all_scopes`, `test_complete_authorization_denied_redirects_with_error`, `test_full_code_exchange_yields_tokens_and_grant`, `test_refresh_rotation_and_replay_revokes` (covers Review Focus 3), `test_load_access_token_none_after_revoke`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat(mcp): oauth authorization server provider`

---

### Task 7: Consent and connection-management routes

**Files:**
- Create: `mealie/mcp/schemas.py`, `mealie/routes/users/mcp_connections.py`
- Modify: `mealie/routes/users/__init__.py` (include router)
- Generate: `task dev:generate`
- Test: `tests/integration_tests/mcp/test_connections_routes.py`

**Interfaces:**
- Schemas (`mealie/mcp/schemas.py`, inherit `MealieModel`): `McpAuthorizeRequestOut(request_id: str, client_name: str | None, client_id: str, scopes: list[str], redirect_host: str)`, `McpAuthorizeDecision(request_id: str, approve: bool)`, `McpAuthorizeRedirect(redirect_url: str)`, `McpConnectionOut(grant_id: str, client_id: str, client_name: str | None, scopes: list[str], created_at: datetime, last_used_at: datetime | None)`.
- Routes (`UserAPIRouter(prefix="/users/mcp", tags=["Users: MCP Connections"])`, controller `BaseUserController`):
  - `GET /api/users/mcp/authorize/{request_id}` → `McpAuthorizeRequestOut` (404 if unknown/expired).
  - `POST /api/users/mcp/authorize` body `McpAuthorizeDecision` → `McpAuthorizeRedirect` (404 if unknown/expired).
  - `GET /api/users/mcp/connections` → `list[McpConnectionOut]` (the user's non-revoked grants).
  - `DELETE /api/users/mcp/connections/{grant_id}` → `SuccessResponse` (404 if not theirs).

- [ ] **Step 1: Tests**: `test_authorize_requires_login` (no header → 401), `test_authorize_get_then_approve_returns_redirect_with_code` (create client + pending via the store, GET then POST approve → `redirect_url` contains `code=` and `state=`), `test_deny_returns_access_denied`, `test_list_and_revoke_connection`, `test_revoked_grant_invalidates_live_access_token` (issue access token via provider, revoke via DELETE, then `await provider.load_access_token(tok) is None`) — Review Focus 4.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement + `task dev:generate`.** **Step 4: Run** → PASS; `task py:lint && task py:mypy` → PASS. **Step 5: Commit** `feat(mcp): consent and connections api routes`

---

### Task 8: Mount the MCP server and OAuth routes in the app

**Files:**
- Create: `mealie/mcp/server.py`, `mealie/mcp/asgi.py`
- Modify: `mealie/app.py` (`lifespan_fn`, `api_routers`)
- Test: `tests/integration_tests/mcp/conftest.py`, `tests/integration_tests/mcp/test_mcp_http.py`

**Interfaces:**
- `mealie/mcp/server.py`: `mcp_server = MCPServer("Mealie", instructions=<3 sentences: what the server does, call get_household_context first, confirm before writing>)`; `class MealieTokenVerifier(TokenVerifier)` whose `verify_token` delegates to `get_provider().load_access_token`.
- `mealie/mcp/asgi.py`: `register_mcp(app: FastAPI) -> None`:
  1. `auth = AuthSettings(issuer_url=BASE_URL, resource_server_url=f"{BASE_URL}/mcp", required_scopes=None, client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=list(ALL_SCOPES), default_scopes=list(ALL_SCOPES)), revocation_options=RevocationOptions(enabled=True), validate_token_resource=False)`.
  2. `app.router.routes.extend(create_auth_routes(provider=get_provider(), issuer_url=..., client_registration_options=..., revocation_options=...))` (paths `/authorize`, `/token`, `/register`, `/revoke`, `/.well-known/oauth-authorization-server`).
  3. `app.router.routes.extend(create_protected_resource_routes(resource_url=f"{BASE_URL}/mcp", authorization_servers=[BASE_URL], scopes_supported=list(ALL_SCOPES)))` (path `/.well-known/oauth-protected-resource/mcp`).
  4. `app.mount("/mcp", mcp_server.streamable_http_app(streamable_http_path="/", auth=auth, token_verifier=MealieTokenVerifier(), json_response=True))`.
  Check exact names/parameters in `mcp.server.auth.routes` and `MCPServer.streamable_http_app` (`uv run python -c "import inspect,mcp.server.auth.routes as r; print(inspect.signature(r.create_auth_routes), inspect.signature(r.create_protected_resource_routes))"`).
- Rate limiting (spec § 4.8): `mealie/mcp/asgi.py: class SimpleRateLimitMiddleware` (in-memory, per IP, 30 requests / 60 s) applied only to the paths `/register`, `/token`, `/authorize`; beyond that → 429. Test `test_register_rate_limited` (31 POSTs → the last one is 429).
- `mealie/app.py`: in `lifespan_fn`, wrap the `yield` in `async with mcp_server.session_manager.run():`; in `api_routers()`, call `register_mcp(app)` after `utility_routes` and **before** `mount_spa`.
- Fixture `mcp_client` (`tests/integration_tests/mcp/conftest.py`): `with TestClient(app) as client: yield client` (the `with` runs the lifespan, required by the session manager; the upstream `api_client` fixture does not). Helper `mcp_bearer(unique_user) -> dict` that creates a grant via the store and issues an access token.
- Test helper `mcp_call(client, headers, method, params) -> dict`: POST `/mcp` JSON-RPC with `Accept: application/json, text/event-stream`, handles `initialize` + `notifications/initialized` then the method.

- [ ] **Step 1: Tests**: `test_well_known_authorization_server` (GET → 200, `issuer == BASE_URL`, `code_challenge_methods_supported` contains `S256`, `registration_endpoint` present), `test_well_known_protected_resource` (`resource` == `{BASE_URL}/mcp`), `test_mcp_without_token_is_401_with_resource_metadata` (`WWW-Authenticate` header contains `resource_metadata=`), `test_mcp_rejects_session_token` (`unique_user.token` → 401) — Review Focus 1, `test_mcp_initialize_with_mcp_token` (→ 200, `serverInfo.name == "Mealie"`), `test_full_oauth_flow_via_http`: `POST /register` (claude redirect_uris) → `GET /authorize` (S256 code_challenge, `follow_redirects=False` → 302 to `/user/connections/authorize?request_id=`) → `POST /api/users/mcp/authorize` approve with `unique_user.token` → `POST /token` (grant_type=authorization_code, code_verifier) → 200 with `access_token` → `initialize` on `/mcp` → 200, `test_register_rate_limited`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; also run `task py:test -- tests/integration_tests/user_tests -q` to check the upstream `api_client` is not broken. **Step 5: Commit** `feat(mcp): mount mcp server and oauth routes`

---

### Task 9: Tool execution context and scope guard

**Files:**
- Create: `mealie/mcp/context.py`, `mealie/mcp/auth.py`, `mealie/mcp/errors.py`
- Test: `tests/unit_tests/mcp/test_context_and_scopes.py`

**Interfaces:**
- `mealie/mcp/errors.py`: `class McpToolError(ToolError)` (SDK `ToolError` — check its v2 import path); `not_found(kind: str, key: str) -> McpToolError`; `forbidden_scope(scope: str) -> McpToolError`.
- `mealie/mcp/context.py`: `@dataclass class McpContext: user: PrivateUser; repos: AllRepositories; session: Session; access: AccessToken`; `@contextmanager def mcp_context() -> Iterator[McpContext]`: `get_access_token()` (None → `McpToolError("unauthenticated")`), opens `session_context()`, loads the user by `access.subject` (absent → error), `repos = get_repositories(session, group_id=user.group_id, household_id=user.household_id)`, commits on clean exit, rolls back otherwise. A function `cross_household_repos(ctx) -> AllRepositories` (`household_id=None`) for group-wide recipe search.
- `mealie/mcp/auth.py`: decorator `require_scope(scope: str)` applicable to tool functions; reads `get_access_token()` and raises `forbidden_scope` if missing. The same decorator logs (logger `mcp`, INFO) `tool=<name> user=<sub> ms=<duration> ok=<bool>` with no arguments or content (spec § 4.8).

- [ ] **Step 1: Tests**: with `monkeypatch` of `mealie.mcp.context.get_access_token` returning an `AccessToken(subject=str(unique_user.user_id), scopes=["recipes:read"], ...)`: `test_context_scopes_repos_to_user_household` (`ctx.repos.household_id == unique_user.household_id`), `test_context_without_token_raises`, `test_require_scope_blocks_missing_scope` (function decorated `mealplan:write` → raises), `test_require_scope_allows_present_scope`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat(mcp): tool execution context and scope guard`

---

### Task 10: Household and recipe tools

**Files:**
- Create: `mealie/mcp/tools/__init__.py`, `mealie/mcp/tools/_summaries.py`, `mealie/mcp/tools/household.py`, `mealie/mcp/tools/recipes.py`
- Modify: `mealie/mcp/server.py` (import `mealie.mcp.tools` to register)
- Test: `tests/unit_tests/mcp/test_tools_recipes.py`

**Interfaces:**
- Convention: each tool is an `async def` decorated `@mcp_server.tool()` + `@require_scope(...)`, which opens `with mcp_context() as ctx:` and delegates to a pure `_impl(ctx, ...)` function testable without HTTP. Returns are serialisable `dict`s (Pydantic `model_dump(mode="json", by_alias=True)`).
- `_summaries.py`: `recipe_brief(r: RecipeSummary, last_made: date | None) -> dict` with keys `id, slug, name, description (≤200 chars), total_time, prep_time, servings, rating, tags: [str], categories: [str], last_made, url (f"{BASE_URL}/g/{group_slug}/r/{slug}")`.
- `household.py`: `get_household_context()` scope `recipes:read` → `{group: {id, name, slug}, household: {id, name}, members: [{id, full_name, username}], user: {id, full_name}, first_day_of_week, locale, today (ISO date, server timezone), scopes_granted: [...]}`. (Profiles/allergies arrive in phase 2; leave an empty `preferences: {}` key.)
- `recipes.py`:
  - `search_recipes(query: str | None = None, tags: list[str] | None = None, categories: list[str] | None = None, max_total_minutes: int | None = None, min_rating: float | None = None, not_made_since_days: int | None = None, order_by: Literal["name","rating","random","last_made","created_at"] = "name", page: int = 1, per_page: int = 20) -> dict` scope `recipes:read`. Implementation: `cross_household_repos(ctx).recipes.by_user(user.id).page_all(PaginationQuery(page, per_page, order_by, order_direction, query_filter=<filter>, pagination_seed=...), tags=tags, categories=categories, require_all_tags=True, search=query)`. Filter built with `QueryFilterBuilder.combine_filters`: `total_time_seconds <= N*60` (when `max_total_minutes`), `rating >= x`, `last_made IS NONE OR last_made <= $NOW-{days}d` (check the exact `IS NULL`/`$NOW-...d` syntax in `mealie/services/query_filter/keywords.py` and the filterable name of the computed last_made column). Return `{items: [recipe_brief], page, per_page, total}`.
  - `get_recipe(slug_or_id: str) -> dict` scope `recipes:read`: full recipe (`Recipe.model_dump`) reduced to `name, slug, description, servings, times, ingredients: [{quantity, unit, food, note, display}], instructions: [{title, text}], tags, categories, tools, notes, org_url, url`.
- [ ] **Step 1: Tests** (upstream fixtures `unique_user`, recipes created via `api_client.post(api_routes.recipes, json={"name": ...})` then PUT for tags/times; context via the Task 9 monkeypatch): `test_get_household_context_shape`, `test_search_by_tag_and_max_time`, `test_search_random_is_seeded_per_call` (two `random` calls do not raise and return the same `total`), `test_get_recipe_by_slug_and_unknown_raises_not_found`, `test_search_only_sees_own_group` (Review Focus 2: a recipe created by a user of another group — upstream `g2_user` fixture — does not appear), `test_search_sees_other_household_same_group` (`h2_user`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat(mcp): household context and recipe tools`

---

### Task 11: Meal-plan tools

**Files:**
- Create: `mealie/mcp/tools/mealplan.py`
- Test: `tests/unit_tests/mcp/test_tools_mealplan.py`

**Interfaces:**
- `get_mealplan(start_date: date, end_date: date) -> dict` scope `recipes:read`: `ctx.repos.meals.get_meals_by_date_range(...)` → `{entries: [{id, date, entry_type, title, text, recipe: recipe_brief | None, servings}]}`.
- `get_recent_meals(days: int = 14) -> dict` scope `recipes:read`: entries from `today-days` to `today`, sorted by date descending, same shape + `recipe_counts: {slug: n}`.
- `add_mealplan_entries(entries: list[MealplanEntryIn]) -> dict` scope `mealplan:write`; `MealplanEntryIn(BaseModel)`: `date: date`, `entry_type: PlanEntryType = "dinner"`, `recipe_slug: str | None = None`, `title: str = ""`, `text: str = ""`, `servings: float | None = None` (→ `recipe_scale = servings / recipe_servings` if both known, else 1.0). Resolve **all** slugs before any write; an unknown slug → `not_found("recipe", slug)` with nothing created (Review Focus 5). Creation via `ctx.repos.meals.create(SavePlanEntry(..., group_id, user_id))`. Return `{created: [entry...], mealplan_url: f"{BASE_URL}/household/mealplan/planner/view"}`.
- `remove_mealplan_entry(entry_id: int) -> dict` scope `mealplan:write`: not found if not in the household.
- [ ] **Step 1: Tests**: `test_add_entries_with_slug_and_free_text`, `test_add_entries_unknown_slug_creates_nothing` (entry count unchanged after the error), `test_servings_computes_scale` (4-serving recipe, `servings=2` → `recipe_scale == 0.5`), `test_get_recent_meals_counts`, `test_remove_entry_other_household_not_found` (entry created by `h2_user`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat(mcp): mealplan tools`

---

### Task 12: Shopping tools

**Files:**
- Create: `mealie/mcp/tools/shopping.py`
- Test: `tests/unit_tests/mcp/test_tools_shopping.py`

**Interfaces:**
- `get_shopping_list(list_id: str | None = None) -> dict` scope `recipes:read`: without `list_id`, the household's most recently updated list; shape `{id, name, url: f"{BASE_URL}/shopping-lists/{id}", items: [{id, checked, quantity, unit, food, note, label, display}], recipe_references: [{recipe_slug, quantity}]}`, items sorted by label then position.
- `create_shopping_list_from_mealplan(start_date: date, end_date: date, list_name: str | None = None, list_id: str | None = None) -> dict` scope `shopping:write`: fetches the period's entries that have a recipe; creates a list (`ShoppingListService(repos).create_one_list(ShoppingListCreate(name=list_name or f"Shopping {start}–{end}"), owner_id=user.id)`) or reuses `list_id`; `add_recipe_ingredients_to_list(list.id, [ShoppingListAddRecipeParamsBulk(recipe_id, recipe_increment_quantity=entry.recipe_scale)])`; return = `get_shopping_list(list.id)` + `recipes_added: [slug]`, `entries_without_recipe: [title]`. (Pantry deduction arrives in phase 2: leave `skipped_from_pantry: []`.)
- `add_shopping_items(list_id: str, items: list[str]) -> dict` scope `shopping:write`: each string becomes an item `note=<text>, is_food=False` via `bulk_create_items`. `check_shopping_items(list_id: str, item_ids: list[str], checked: bool = True) -> dict`.
- [ ] **Step 1: Tests** (upstream `shopping_lists`/`unique_user` fixtures, a recipe with 2 ingredients): `test_create_list_from_mealplan_adds_recipe_ingredients` (2 items, `recipe_references` contains the slug), `test_reuse_existing_list_merges`, `test_add_and_check_items`, `test_get_default_list_is_most_recent`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; full `task py:check` → PASS. **Step 5: Commit** `feat(mcp): shopping list tools`

---

### Task 13: Frontend — Connections page and consent page

**Files:**
- Create: `frontend/app/lib/api/user/mcp-connections.ts`, `frontend/app/pages/user/connections/index.vue`, `frontend/app/pages/user/connections/authorize.vue`
- Modify: `frontend/app/lib/api/index.ts` (expose `mcpConnections`), `frontend/app/pages/user/profile/index.vue:104-118` (add a `UserProfileLinkCard` "Claude & MCP connections" → `/user/connections`), `frontend/app/lang/messages/en-US.json` and `fr-FR.json` (`settings.mcp.*` keys)
- Types: `frontend/app/lib/api/types/` regenerated by `task dev:generate` (do not edit)
- Test: no unit test required; verification via `task ui:lint` and manual test

**Interfaces:**
- `McpConnectionsApi extends BaseAPI`: `getAuthorizeRequest(requestId: string)`, `decide(requestId: string, approve: boolean)`, `getConnections()`, `revoke(grantId: string)`; routes `/api/users/mcp/...` from Task 7.
- `authorize.vue`: `definePageMeta({ layout: "basic" })`; reads `route.query.request_id`; if not logged in (`useAuthBackend().loggedIn` false) → `navigateTo({ path: "/login", query: { redirect: route.fullPath } })`; shows client name (or `client_id`), redirect host, list of translated scopes; Approve / Deny buttons → `decide()` then `window.location.assign(redirect_url)`. Unknown request → "request expired" message + back button.
- `index.vue`: table of connections (client, scopes, created, last used) + Revoke button with confirmation (upstream `BaseDialog`). "How to connect Claude" box: URL to paste = `${BASE_URL}/mcp`.
- i18n keys: `settings.mcp.title`, `settings.mcp.description`, `settings.mcp.authorize-title`, `settings.mcp.authorize-text` (`{client} wants to access your Mealie account`), `settings.mcp.scope.recipes-read` … (5), `settings.mcp.approve`, `settings.mcp.deny`, `settings.mcp.expired`, `settings.mcp.no-connections`, `settings.mcp.revoke`, `settings.mcp.last-used`, `settings.mcp.how-to`.

- [ ] **Step 1: `task dev:generate`** then create the API client. **Step 2: Pages + i18n + profile link.** **Step 3: `task ui:lint`** → PASS. **Step 4: Manual test**: `task py` + `task ui`, create a client via `curl -X POST localhost:9000/register -d '{"redirect_uris":["http://localhost:3000/cb"],"client_name":"Test"}'`, open `http://localhost:9000/authorize?response_type=code&client_id=...&redirect_uri=http://localhost:3000/cb&code_challenge=...&code_challenge_method=S256&state=x` (the dev SPA is on :3000: replace the consent URL base with :3000 by hand), check consent → redirect with `code`. **Step 5: Commit** `feat(ui): mcp connections and consent pages`

---

### Task 14: Docker Compose, GHCR image, deployment docs

**Files:**
- Create: `docker-compose.yml` (root), `.env.example`, `.github/workflows/fork-image.yml`, `docs/fork/deploy.md`
- Modify: `docker/healthcheck.sh` (add a GET `/.well-known/oauth-protected-resource/mcp` → 200), `README.md` (link to `docs/fork/deploy.md`)

- [ ] **Step 1: `docker-compose.yml`**: services `mealie` (`image: ghcr.io/christophe668/mealie:main`, `build: {context: ., dockerfile: docker/Dockerfile, target: production}`, `ports: ["9925:9000"]`, env `BASE_URL=${BASE_URL}`, `DB_ENGINE=postgres`, `POSTGRES_*`, `ALLOW_SIGNUP=false`, `TZ=Europe/Brussels`, volume `mealie-data:/app/data`, `depends_on: postgres: condition: service_healthy`) and `postgres` (`postgres:17-alpine`, volume, `pg_isready` healthcheck). `.env.example` with `BASE_URL=https://mealie.example.com` and passwords to change.
- [ ] **Step 2: Workflow** `fork-image.yml`: `on: push: branches: [main], tags: ["v*"]`; `docker/login-action` GHCR with `GITHUB_TOKEN`; `docker/metadata-action` images `ghcr.io/${{ github.repository }}` tags `main`, `sha`, semver; `docker/build-push-action` `file: docker/Dockerfile`, `target: production`, `platforms: linux/amd64,linux/arm64`, GHA cache. Disable upstream workflows that are useless in the fork: in the fork's GitHub settings, disable Actions then re-enable only `fork-image.yml` and `test-backend.yml` (`gh workflow disable <name>` for the others).
- [ ] **Step 3: `docs/fork/deploy.md`**: prerequisites (domain, HTTPS), two reverse-proxy examples: Caddyfile (`mealie.example.com { reverse_proxy localhost:9925 }`) and Cloudflare Tunnel (`cloudflared tunnel ... --url http://localhost:9925`); "Add to claude.ai" steps: Settings → Connectors → Add custom connector → URL `https://<domain>/mcp` → sign in → approve; check `curl https://<domain>/.well-known/oauth-authorization-server`.
- [ ] **Step 4: Verify locally**: `BASE_URL=http://localhost:9925 docker compose up -d --build`; `curl -s localhost:9925/.well-known/oauth-protected-resource/mcp | jq .resource` → `"http://localhost:9925/mcp"`; `docker compose ps` → `mealie` healthy. Then `docker compose down -v`.
- [ ] **Step 5: Commit + push** `ci: build fork image on ghcr and add deployment docs`; check `gh run watch` → image published (`gh api /user/packages/container/mealie/versions | jq length` ≥ 1).

---

### Task 15: End-to-end test from claude.ai

**Files:**
- Modify: `docs/fork/deploy.md` ("Acceptance checklist" section)

- [ ] **Step 1:** Deploy the image on the target machine (or run locally + temporary tunnel `cloudflared tunnel --url http://localhost:9925` with `BASE_URL` = the tunnel URL).
- [ ] **Step 2:** In claude.ai (web), add the connector `https://<url>/mcp`; sign in; approve consent; check the connection appears in `/user/connections`.
- [ ] **Step 3:** In a conversation: "Give me my household context and 3 random recipes" → `get_household_context` then `search_recipes(order_by="random")` are called with correct answers. "Plan <recipe> for tomorrow evening and make the shopping list" → entry visible in the Mealie planner, list visible in Shopping.
- [ ] **Step 4:** Repeat step 3 from the claude.ai mobile app.
- [ ] **Step 5:** Revoke the connection in Mealie; check Claude gets an authentication error on the next call and offers to reconnect.
- [ ] **Step 6:** Record the result (OK / deviations) at the end of `docs/fork/deploy.md`, commit `docs: phase 1 acceptance checklist`.
