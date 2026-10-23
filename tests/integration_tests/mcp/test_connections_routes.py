import asyncio
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy.orm import Session

from mealie.mcp.oauth.provider import get_provider
from mealie.mcp.oauth.store import OAuthStore
from mealie.mcp.oauth.tokens import issue_access_token
from tests.utils import api_routes
from tests.utils.factories import random_string

CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def _make_client(store: OAuthStore) -> OAuthClientInformationFull:
    client = OAuthClientInformationFull(
        client_id=random_string(),
        client_name="Claude",
        redirect_uris=[CALLBACK],
        token_endpoint_auth_method="none",
    )
    store.save_client(client)
    return client


def _make_pending(store: OAuthStore, client: OAuthClientInformationFull) -> str:
    params = AuthorizationParams(
        state="s1",
        scopes=["recipes:read"],
        code_challenge="challenge",
        redirect_uri=CALLBACK,
        redirect_uri_provided_explicitly=True,
        resource="https://mealie.example/mcp",
    )
    return store.create_pending(client.client_id, params)


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_authorize_requires_login(api_client: TestClient):
    assert api_client.get(api_routes.users_mcp_authorize_request_id("abc")).status_code == 401
    body = {"requestId": "abc", "approve": True}
    assert api_client.post(api_routes.users_mcp_authorize, json=body).status_code == 401
    assert api_client.get(api_routes.users_mcp_connections).status_code == 401


def test_authorize_get_then_approve_returns_redirect_with_code(api_client: TestClient, unique_user, session: Session):
    store = OAuthStore(session)
    client = _make_client(store)
    request_id = _make_pending(store, client)

    response = api_client.get(api_routes.users_mcp_authorize_request_id(request_id), headers=unique_user.token)
    assert response.status_code == 200
    data = response.json()
    assert data["requestId"] == request_id
    assert data["clientId"] == client.client_id
    assert data["clientName"] == "Claude"
    assert data["scopes"] == ["recipes:read"]
    assert data["redirectHost"] == "claude.ai"

    response = api_client.post(
        api_routes.users_mcp_authorize,
        json={"requestId": request_id, "approve": True},
        headers=unique_user.token,
    )
    assert response.status_code == 200
    query = _query(response.json()["redirectUrl"])
    assert "code" in query
    assert query["state"] == "s1"

    # the pending request is consumed
    assert (
        api_client.get(api_routes.users_mcp_authorize_request_id(request_id), headers=unique_user.token).status_code
        == 404
    )


def test_unknown_request_is_404(api_client: TestClient, unique_user):
    assert (
        api_client.get(api_routes.users_mcp_authorize_request_id("nope"), headers=unique_user.token).status_code == 404
    )
    response = api_client.post(
        api_routes.users_mcp_authorize, json={"requestId": "nope", "approve": True}, headers=unique_user.token
    )
    assert response.status_code == 404


def test_deny_returns_access_denied(api_client: TestClient, unique_user, session: Session):
    store = OAuthStore(session)
    request_id = _make_pending(store, _make_client(store))

    response = api_client.post(
        api_routes.users_mcp_authorize,
        json={"requestId": request_id, "approve": False},
        headers=unique_user.token,
    )

    assert response.status_code == 200
    query = _query(response.json()["redirectUrl"])
    assert query == {"error": "access_denied", "state": "s1"}


def test_list_and_revoke_connection(api_client: TestClient, unique_user, session: Session):
    store = OAuthStore(session)
    client = _make_client(store)
    grant = store.create_grant(user_id=unique_user.user_id, client_id=client.client_id, scopes=["recipes:read"])

    response = api_client.get(api_routes.users_mcp_connections, headers=unique_user.token)
    assert response.status_code == 200
    items = response.json()
    assert [i["grantId"] for i in items] == [grant.grant_id]
    assert items[0]["clientName"] == "Claude"
    assert items[0]["scopes"] == ["recipes:read"]
    assert items[0]["lastUsedAt"] is None

    response = api_client.delete(api_routes.users_mcp_connections_grant_id(grant.grant_id), headers=unique_user.token)
    assert response.status_code == 200
    assert api_client.get(api_routes.users_mcp_connections, headers=unique_user.token).json() == []
    assert (
        api_client.delete(
            api_routes.users_mcp_connections_grant_id(grant.grant_id), headers=unique_user.token
        ).status_code
        == 404
    )


def test_cannot_revoke_another_users_grant(api_client: TestClient, unique_user, h2_user, session: Session):
    store = OAuthStore(session)
    client = _make_client(store)
    grant = store.create_grant(user_id=unique_user.user_id, client_id=client.client_id, scopes=["recipes:read"])

    response = api_client.delete(api_routes.users_mcp_connections_grant_id(grant.grant_id), headers=h2_user.token)

    assert response.status_code == 404
    assert store.get_grant(grant.grant_id) is not None


def test_revoked_grant_invalidates_live_access_token(api_client: TestClient, unique_user, session: Session):
    store = OAuthStore(session)
    client = _make_client(store)
    grant = store.create_grant(user_id=unique_user.user_id, client_id=client.client_id, scopes=["recipes:read"])
    token, _ = issue_access_token(
        user_id=str(unique_user.user_id),
        client_id=client.client_id,
        grant_id=grant.grant_id,
        scopes=["recipes:read"],
        resource=None,
    )
    provider = get_provider()
    assert asyncio.run(provider.load_access_token(token)) is not None

    response = api_client.delete(api_routes.users_mcp_connections_grant_id(grant.grant_id), headers=unique_user.token)

    assert response.status_code == 200
    assert asyncio.run(provider.load_access_token(token)) is None
