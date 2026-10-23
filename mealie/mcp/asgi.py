import threading
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import ClassVar
from urllib.parse import urlparse

from fastapi import FastAPI
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mealie.core.config import get_app_settings
from mealie.core.root_logger import get_logger
from mealie.mcp.oauth.provider import get_provider
from mealie.mcp.scopes import ALL_SCOPES
from mealie.mcp.server import mcp_server

MCP_PATH = "/mcp"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

logger = get_logger()


def mcp_enabled(base_url: str) -> bool:
    """The OAuth issuer must be https (the SDK refuses anything else except on loopback)."""
    parsed = urlparse(base_url)
    return parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS)


class SimpleRateLimitMiddleware:
    """In-memory sliding-window limit on the public OAuth endpoints: per client IP, plus a global ceiling.

    The key is `scope["client"]`, which uvicorn rewrites from `X-Forwarded-For` for every proxy listed in
    `forwarded_allow_ips` (Mealie's `HOST_IP`, `*` by default). Per-IP accuracy therefore requires `HOST_IP`
    narrowed to the reverse proxy; otherwise clients can pick their own key. The key cap and the global
    ceiling bound memory and total throughput even then.

    State is process-local: with several workers each one counts separately.
    """

    LIMITED_PATHS: ClassVar[frozenset[str]] = frozenset({"/register", "/token", "/authorize"})
    LIMIT: ClassVar[int] = 30
    GLOBAL_LIMIT: ClassVar[int] = 600
    WINDOW_SECONDS: ClassVar[float] = 60.0
    MAX_KEYS: ClassVar[int] = 10_000

    # ordered by most recent hit (least recent first), so expired keys are always at the front
    _hits: ClassVar[OrderedDict[str, deque[float]]] = OrderedDict()
    _global_hits: ClassVar[deque[float]] = deque()
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._hits.clear()
            cls._global_hits.clear()

    @classmethod
    def tracked_keys(cls) -> int:
        with cls._lock:
            return len(cls._hits)

    @staticmethod
    def _clock() -> float:
        return time.monotonic()

    @classmethod
    def allow(cls, key: str) -> bool:
        """Records a request for `key`; returns False when the per-key or the global limit is reached."""
        now = cls._clock()
        horizon = now - cls.WINDOW_SECONDS
        with cls._lock:
            # drop keys whose most recent hit is outside the window (they sit at the front)
            while cls._hits:
                oldest_key, oldest_hits = next(iter(cls._hits.items()))
                if oldest_hits[-1] > horizon:
                    break
                del cls._hits[oldest_key]
            while cls._global_hits and cls._global_hits[0] <= horizon:
                cls._global_hits.popleft()

            hits = cls._hits.get(key)
            if hits is not None:
                while hits[0] <= horizon:
                    hits.popleft()
                if len(hits) >= cls.LIMIT:
                    return False
            if len(cls._global_hits) >= cls.GLOBAL_LIMIT:
                return False

            if hits is None:
                hits = cls._hits[key] = deque()
            hits.append(now)
            cls._hits.move_to_end(key)
            cls._global_hits.append(now)
            while len(cls._hits) > cls.MAX_KEYS:
                cls._hits.popitem(last=False)
            return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in self.LIMITED_PATHS:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        if not self.allow(key):
            response = JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": "60"})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class _McpApp:
    """ASGI endpoint for `/mcp` that delegates to the SDK's streamable HTTP app.

    The transport is stateless (no `mcp-session-id`), so any worker can serve any request.
    The SDK's session manager can only be run once, so the app is rebuilt whenever the Mealie lifespan
    runs again (this only happens in tests, where every `with TestClient(app)` starts a new lifespan).
    """

    def __init__(self) -> None:
        self._app: Starlette | None = None
        self._started = False

    def build(self) -> None:
        self._app = mcp_server.streamable_http_app(
            streamable_http_path=MCP_PATH,
            json_response=True,
            stateless_http=True,
            # DNS-rebinding protection only matters for servers bound to localhost and reached from a
            # browser; Mealie runs behind a reverse proxy that validates the Host header, and the
            # endpoint requires a bearer token, so the SDK check is disabled instead of pinning hosts.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        if self._app is None:  # MCP is disabled (see register_mcp), nothing to run
            yield
            return
        if self._started:
            self.build()
        self._started = True
        async with mcp_server.session_manager.run():
            yield

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._app is None:
            raise RuntimeError("the MCP app is not built, register_mcp() must run first")
        await self._app(scope, receive, send)


mcp_app = _McpApp()


def mcp_lifespan() -> AbstractAsyncContextManager[None]:
    """Runs the MCP session manager; to be entered from the Mealie app lifespan."""
    return mcp_app.run()


def register_mcp(app: FastAPI) -> None:
    """Adds the OAuth authorization server, the protected-resource metadata and the `/mcp` endpoint.

    Registers nothing (with a warning) when BASE_URL is plain http on a non-loopback host.
    Must run before the SPA is mounted, since the SPA catches every unmatched path.
    """
    base_url = get_app_settings().BASE_URL
    if not mcp_enabled(base_url):
        logger.warning(f"MCP/OAuth disabled: BASE_URL must be https (or localhost), current: {base_url}")
        return

    auth = mcp_server.settings.auth
    if auth is None or auth.resource_server_url is None:
        raise RuntimeError("the MCP server must be configured with auth settings")

    app.router.routes.extend(
        create_auth_routes(
            provider=get_provider(),
            issuer_url=auth.issuer_url,
            client_registration_options=auth.client_registration_options,
            revocation_options=auth.revocation_options,
        )
    )
    app.router.routes.extend(
        create_protected_resource_routes(
            resource_url=auth.resource_server_url,
            authorization_servers=[auth.issuer_url],
            scopes_supported=list(ALL_SCOPES),
        )
    )

    # a Route rather than app.mount("/mcp"): a Mount only matches "/mcp/..." and would answer the bare
    # "/mcp" with a redirect, which MCP clients do not follow on POST
    mcp_app.build()
    app.router.routes.append(Route(MCP_PATH, endpoint=mcp_app))

    app.add_middleware(SimpleRateLimitMiddleware)
