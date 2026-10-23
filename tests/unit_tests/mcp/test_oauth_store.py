from datetime import timedelta

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy import select
from sqlalchemy.orm import Session

from mealie.db.models.mcp.oauth import McpOAuthCode, McpOAuthPendingAuth, McpOAuthRefreshToken
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


def _grant_and_token(store: OAuthStore, user) -> tuple[str, str]:
    grant = store.create_grant(user_id=user.user_id, client_id="c1", scopes=["recipes:read"])
    raw = store.create_refresh_token(grant_id=grant.grant_id, client_id="c1", scopes=["recipes:read"], resource=None)
    return grant.grant_id, raw


def test_refresh_token_stored_hashed(session: Session, unique_user):
    store = OAuthStore(session)
    _, raw = _grant_and_token(store, unique_user)

    stored = session.scalars(
        select(McpOAuthRefreshToken).where(McpOAuthRefreshToken.token_hash == tokens.hash_token(raw))
    ).first()
    assert stored is not None
    assert stored.token_hash != raw
    assert session.scalars(select(McpOAuthRefreshToken).where(McpOAuthRefreshToken.token_hash == raw)).first() is None


def test_refresh_replay_deletes_family_tokens(session: Session, unique_user):
    store = OAuthStore(session)
    grant_id, raw = _grant_and_token(store, unique_user)
    other = store.create_refresh_token(grant_id=grant_id, client_id="c1", scopes=["recipes:read"], resource=None)

    assert store.consume_refresh_token(raw) is not None
    assert store.consume_refresh_token(raw) is None

    assert store.get_grant(grant_id) is None
    assert store.consume_refresh_token(other) is None
    remaining = session.scalars(select(McpOAuthRefreshToken).where(McpOAuthRefreshToken.grant_id == grant_id)).all()
    assert remaining == []


def test_expired_code_returns_none_and_is_deleted(session: Session, unique_user, monkeypatch):
    monkeypatch.setattr(tokens, "AUTH_CODE_TTL", timedelta(seconds=-1))
    store = OAuthStore(session)
    code = store.create_code(client_id="c1", user_id=unique_user.user_id, params=_params())

    assert store.pop_code(code) is None
    assert session.scalars(select(McpOAuthCode).where(McpOAuthCode.code == code)).first() is None


def test_expired_refresh_token_returns_none(session: Session, unique_user, monkeypatch):
    monkeypatch.setattr(tokens, "REFRESH_TOKEN_TTL", timedelta(seconds=-1))
    store = OAuthStore(session)
    grant_id, raw = _grant_and_token(store, unique_user)

    assert store.consume_refresh_token(raw) is None
    assert store.get_grant(grant_id) is not None


def test_confidential_client_roundtrip(session: Session):
    info = OAuthClientInformationFull(
        client_id=random_string(),
        client_secret="s3cret",
        redirect_uris=[CALLBACK],
        token_endpoint_auth_method="client_secret_post",
    )
    store = OAuthStore(session)
    store.save_client(info)

    loaded = store.get_client(info.client_id)
    assert loaded is not None
    assert loaded.client_secret == "s3cret"


def test_save_client_updates_existing(session: Session):
    store = OAuthStore(session)
    info = _client()
    store.save_client(info)
    store.save_client(info.model_copy(update={"client_name": "Renamed"}))

    loaded = store.get_client(info.client_id)
    assert loaded is not None
    assert loaded.client_name == "Renamed"


def test_list_and_touch_grants(session: Session, unique_user):
    store = OAuthStore(session)
    grant = store.create_grant(user_id=unique_user.user_id, client_id="c1", scopes=["recipes:read"])
    assert grant.last_used_at is None

    store.touch_grant(grant.grant_id)

    listed = [g.grant_id for g in store.list_grants(unique_user.user_id)]
    assert grant.grant_id in listed
    refreshed = store.get_grant(grant.grant_id)
    assert refreshed is not None and refreshed.last_used_at is not None

    store.revoke_grant(grant.grant_id, unique_user.user_id)
    assert grant.grant_id not in [g.grant_id for g in store.list_grants(unique_user.user_id)]


def test_purge_expired(session: Session, unique_user, monkeypatch):
    store = OAuthStore(session)
    live_pending = store.create_pending("c1", _params())
    live_code = store.create_code(client_id="c1", user_id=unique_user.user_id, params=_params())
    monkeypatch.setattr(tokens, "PENDING_AUTH_TTL", timedelta(seconds=-1))
    monkeypatch.setattr(tokens, "AUTH_CODE_TTL", timedelta(seconds=-1))
    dead_pending = store.create_pending("c1", _params())
    dead_code = store.create_code(client_id="c1", user_id=unique_user.user_id, params=_params())

    store.purge_expired()

    def has_pending(rid: str) -> bool:
        return (
            session.scalars(select(McpOAuthPendingAuth).where(McpOAuthPendingAuth.request_id == rid)).first()
            is not None
        )

    def has_code(c: str) -> bool:
        return session.scalars(select(McpOAuthCode).where(McpOAuthCode.code == c)).first() is not None

    assert has_pending(live_pending) and not has_pending(dead_pending)
    assert has_code(live_code) and not has_code(dead_code)


def test_peek_code_does_not_consume(session: Session, unique_user):
    store = OAuthStore(session)
    code = store.create_code(client_id="c1", user_id=unique_user.user_id, params=_params())

    assert store.peek_code(code) is not None
    assert store.peek_code(code) is not None
    assert store.pop_code(code) is not None
    assert store.peek_code(code) is None


def test_peek_refresh_token_is_read_only(session: Session, unique_user):
    store = OAuthStore(session)
    _, raw = _grant_and_token(store, unique_user)

    assert store.peek_refresh_token(raw) is not None
    assert store.peek_refresh_token("nope") is None
    assert store.consume_refresh_token(raw) is not None
    assert store.peek_refresh_token(raw) is None


def test_revoke_grant_by_id(session: Session, unique_user):
    store = OAuthStore(session)
    grant_id, raw = _grant_and_token(store, unique_user)

    store.revoke_grant_by_id(grant_id)
    store.revoke_grant_by_id("missing")

    assert store.get_grant(grant_id) is None
    assert store.peek_refresh_token(raw) is None
