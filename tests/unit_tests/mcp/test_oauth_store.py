from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy.orm import Session

from mealie.mcp.oauth import tokens
from mealie.mcp.oauth.store import OAuthStore
from tests.utils.factories import random_string

CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def _client(client_id: str | None = None) -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id or random_string(),
        client_name="Claude",
        redirect_uris=[CALLBACK],
        token_endpoint_auth_method="none",
    )


def _params() -> AuthorizationParams:
    return AuthorizationParams(
        state="s1",
        scopes=["recipes:read"],
        code_challenge="challenge",
        redirect_uri=CALLBACK,
        redirect_uri_provided_explicitly=True,
        resource="https://mealie.example/mcp",
    )


def test_client_roundtrip(session: Session):
    store = OAuthStore(session)
    info = _client()
    assert store.get_client(info.client_id) is None

    store.save_client(info)

    assert store.get_client(info.client_id) == info


def test_pending_pop_is_single_use(session: Session):
    store = OAuthStore(session)
    request_id = store.create_pending("c1", _params())

    assert store.peek_pending(request_id) is not None
    popped = store.pop_pending(request_id)
    assert popped == ("c1", _params())
    assert store.pop_pending(request_id) is None
    assert store.peek_pending(request_id) is None


def test_pending_expired_returns_none(session: Session, monkeypatch):
    monkeypatch.setattr(tokens, "PENDING_AUTH_TTL", -tokens.PENDING_AUTH_TTL)
    store = OAuthStore(session)
    request_id = store.create_pending("c1", _params())

    assert store.peek_pending(request_id) is None
    assert store.pop_pending(request_id) is None


def test_code_pop_single_use(session: Session, unique_user):
    store = OAuthStore(session)
    code = store.create_code(client_id="c1", user_id=unique_user.user_id, params=_params())

    row = store.pop_code(code)
    assert row is not None
    assert row.client_id == "c1"
    assert row.redirect_uri == CALLBACK
    assert row.scopes == ["recipes:read"]
    assert store.pop_code(code) is None


def test_refresh_reuse_revokes_grant(session: Session, unique_user):
    store = OAuthStore(session)
    grant = store.create_grant(user_id=unique_user.user_id, client_id="c1", scopes=["recipes:read"])
    raw = store.create_refresh_token(grant_id=grant.grant_id, client_id="c1", scopes=["recipes:read"], resource=None)

    assert store.consume_refresh_token(raw) is not None
    assert store.consume_refresh_token(raw) is None
    assert store.get_grant(grant.grant_id) is None


def test_revoke_grant_only_by_owner(session: Session, unique_user, h2_user):
    store = OAuthStore(session)
    grant = store.create_grant(user_id=unique_user.user_id, client_id="c1", scopes=["recipes:read"])

    assert store.revoke_grant(grant.grant_id, h2_user.user_id) is False
    assert store.get_grant(grant.grant_id) is not None
    assert store.revoke_grant(grant.grant_id, unique_user.user_id) is True
    assert store.get_grant(grant.grant_id) is None
