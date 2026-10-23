import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import ClassVar

from fastapi import FastAPI
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mealie.mcp.oauth.provider import get_provider
from mealie.mcp.scopes import ALL_SCOPES
from mealie.mcp.server import mcp_server

MCP_PATH = "/mcp"


class SimpleRateLimitMiddleware:
    """In-memory, per-client-IP sliding-window limit on the public OAuth endpoints.

    State is process-local: with several workers each one counts separately, which is acceptable for a
    single-container deployment.
    """

    LIMITED_PATHS: ClassVar[frozenset[str]] = frozenset({"/register", "/token", "/authorize"})
    LIMIT: ClassVar[int] = 30
    WINDOW_SECONDS: ClassVar[float] = 60.0

    _hits: ClassVar[defaultdict[str, deque[float]]] = defaultdict(deque)
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._hits.clear()

    @classmethod
    def _allow(cls, key: str) -> bool:
        now = time.monotonic()
        with cls._lock:
            hits = cls._hits[key]
            while hits and now - hits[0] >= cls.WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= cls.LIMIT:
                return False
            hits.append(now)
            return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in self.LIMITED_PATHS:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        if not self._allow(key):
            response = JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": "60"})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class _McpApp:
    """ASGI endpoint for `/mcp` that delegates to the SDK's streamable HTTP app.

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
            # DNS-rebinding protection only matters for servers bound to localhost and reached from a
            # browser; Mealie runs behind a reverse proxy that validates the Host header, and the
            # endpoint requires a bearer token, so the SDK check is disabled instead of pinning hosts.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        if self._app is None or self._started:
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

    Must run before the SPA is mounted, since the SPA catches every unmatched path.
    """
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
