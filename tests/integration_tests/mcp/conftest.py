from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mealie.app import app
from mealie.mcp.oauth.store import OAuthStore
from mealie.mcp.oauth.tokens import issue_access_token
from mealie.mcp.scopes import ALL_SCOPES
from tests.utils.fixture_schemas import TestUser

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
PROTOCOL_VERSION = "2025-06-18"


@pytest.fixture(autouse=True)
def reset_rate_limit() -> Generator[None]:
    """The rate limiter is process-wide and every test client shares one IP, so each test starts clean."""
    from mealie.mcp.asgi import SimpleRateLimitMiddleware

    SimpleRateLimitMiddleware.reset()
    yield
    SimpleRateLimitMiddleware.reset()


@pytest.fixture()
def mcp_client(api_client: TestClient) -> Generator[TestClient]:
    """A client that runs the app lifespan, which the MCP session manager needs (the upstream `api_client` does not)."""
    with TestClient(app) as client:
        yield client


def make_mcp_bearer(session: Session, user: TestUser, scopes: list[str] | None = None) -> dict[str, str]:
    scopes = list(scopes if scopes is not None else ALL_SCOPES)
    grant = OAuthStore(session).create_grant(user_id=user.user_id, client_id="test-client", scopes=scopes)
    token, _ = issue_access_token(
        user_id=str(user.user_id),
        client_id="test-client",
        grant_id=grant.grant_id,
        scopes=scopes,
        resource=None,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def mcp_bearer(session: Session, unique_user: TestUser) -> dict[str, str]:
    return make_mcp_bearer(session, unique_user)


def _rpc(client: TestClient, headers: dict[str, str], payload: dict[str, Any]) -> Any:
    return client.post("/mcp", json=payload, headers={**MCP_HEADERS, **headers})


def mcp_initialize(client: TestClient, headers: dict[str, str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Runs the MCP handshake; returns the initialize result and the headers to use for the session."""
    response = _rpc(
        client,
        headers,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        },
    )
    assert response.status_code == 200, response.text
    session_headers = dict(headers)
    if session_id := response.headers.get("mcp-session-id"):
        session_headers["mcp-session-id"] = session_id
    session_headers["mcp-protocol-version"] = PROTOCOL_VERSION

    notified = _rpc(client, session_headers, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notified.status_code == 202, notified.text
    return response.json()["result"], session_headers


def mcp_call(client: TestClient, headers: dict[str, str], method: str, params: dict[str, Any] | None = None) -> dict:
    """Initializes an MCP session, then sends one JSON-RPC request and returns the full response body."""
    _, session_headers = mcp_initialize(client, headers)
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 2, "method": method}
    if params is not None:
        payload["params"] = params
    response = _rpc(client, session_headers, payload)
    assert response.status_code == 200, response.text
    return response.json()
