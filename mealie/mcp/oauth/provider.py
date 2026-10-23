import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from functools import lru_cache
from typing import cast

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from sqlalchemy.orm import Session

from mealie.core.config import get_app_settings
from mealie.db.db_setup import session_context
from mealie.db.models._model_utils.guid import GUID
from mealie.mcp.oauth import tokens
from mealie.mcp.oauth.store import OAuthStore
from mealie.mcp.scopes import ALL_SCOPES


class McpAuthCode(AuthorizationCode):
    user_id: str


class MealieOAuthProvider(OAuthAuthorizationServerProvider[McpAuthCode, RefreshToken, AccessToken]):
    """OAuth authorization server for the MCP endpoint, backed by `OAuthStore`.

    The SDK's provider methods are async while the store is synchronous; the queries are short, so they run inline.
    """

    def __init__(self, session_factory: Callable[[], AbstractContextManager[Session]] = session_context) -> None:
        self._session_factory = session_factory

    # clients

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._session_factory() as session:
            return OAuthStore(session).get_client(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        with self._session_factory() as session:
            OAuthStore(session).save_client(client_info)

    # authorization

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not params.scopes:
            params = params.model_copy(update={"scopes": list(ALL_SCOPES)})
        if client.client_id is None:
            raise ValueError("client_id is required")

        with self._session_factory() as session:
            request_id = OAuthStore(session).create_pending(client.client_id, params)

        return f"{get_app_settings().BASE_URL.rstrip('/')}/user/connections/authorize?request_id={request_id}"

    def complete_authorization(self, request_id: str, user_id: str, approve: bool) -> str:
        """Finishes a pending authorization once the user has decided; returns the client redirect URL.

        Not part of the SDK protocol, it is called by the consent route.

        Raises:
            KeyError: if the request is unknown, expired or already completed.
        """
        with self._session_factory() as session:
            store = OAuthStore(session)
            pending = store.pop_pending(request_id)
            if pending is None:
                raise KeyError(request_id)

            client_id, params = pending
            redirect_uri = str(params.redirect_uri)
            if not approve:
                return construct_redirect_uri(redirect_uri, error="access_denied", state=params.state)

            code = store.create_code(client_id=client_id, user_id=cast(GUID, uuid.UUID(user_id)), params=params)
            return construct_redirect_uri(redirect_uri, code=code, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> McpAuthCode | None:
        # read-only: the SDK verifies PKCE after this call, consumption happens in the exchange
        with self._session_factory() as session:
            row = OAuthStore(session).peek_code(authorization_code)
            if row is None or row.client_id != client.client_id:
                return None

            return McpAuthCode(
                code=row.code,
                scopes=list(row.scopes),
                expires_at=row.expires_at.timestamp(),
                client_id=row.client_id,
                code_challenge=row.code_challenge,
                redirect_uri=AnyUrl(row.redirect_uri),
                redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
                resource=row.resource,
                subject=str(row.user_id),
                user_id=str(row.user_id),
            )

    def _issue(
        self,
        store: OAuthStore,
        *,
        user_id: str,
        client_id: str,
        grant_id: str,
        scopes: list[str],
        resource: str | None,
    ) -> OAuthToken:
        access_token, _ = tokens.issue_access_token(
            user_id=user_id, client_id=client_id, grant_id=grant_id, scopes=scopes, resource=resource
        )
        refresh = store.create_refresh_token(grant_id=grant_id, client_id=client_id, scopes=scopes, resource=resource)
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=int(tokens.ACCESS_TOKEN_TTL.total_seconds()),
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: McpAuthCode
    ) -> OAuthToken:
        with self._session_factory() as session:
            store = OAuthStore(session)
            # atomic claim: a code that was already used (or expired meanwhile) yields nothing
            row = store.pop_code(authorization_code.code)
            if row is None or row.client_id != client.client_id:
                raise TokenError(error="invalid_grant", error_description="authorization code is invalid or used")

            scopes = list(row.scopes)
            grant = store.create_grant(user_id=row.user_id, client_id=row.client_id, scopes=scopes)
            return self._issue(
                store,
                user_id=str(row.user_id),
                client_id=row.client_id,
                grant_id=grant.grant_id,
                scopes=scopes,
                resource=row.resource,
            )

    # refresh

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        # read-only: rotation happens in exchange_refresh_token
        with self._session_factory() as session:
            store = OAuthStore(session)
            row = store.peek_refresh_token(refresh_token)
            if row is None or row.client_id != client.client_id:
                return None

            grant = store.get_grant(row.grant_id)
            if grant is None:
                return None

            return RefreshToken(
                token=refresh_token,
                client_id=row.client_id,
                scopes=list(row.scopes),
                expires_at=int(row.expires_at.timestamp()),
                resource=row.resource,
                subject=str(grant.user_id),
            )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        with self._session_factory() as session:
            store = OAuthStore(session)
            current = store.peek_refresh_token(refresh_token.token)
            grant = store.get_grant(current.grant_id) if current else None

            # a spent token still has to reach consume_refresh_token so that replay revokes the grant
            if current is None:
                store.consume_refresh_token(refresh_token.token)
                raise TokenError(error="invalid_grant", error_description="refresh token is invalid or used")
            if grant is None:
                raise TokenError(error="invalid_grant", error_description="grant has been revoked")

            requested = scopes or list(grant.scopes)
            if any(scope not in grant.scopes for scope in requested):
                raise TokenError(error="invalid_scope", error_description="scope exceeds the granted scopes")

            row = store.consume_refresh_token(refresh_token.token)
            if row is None:
                raise TokenError(error="invalid_grant", error_description="refresh token is invalid or used")

            return self._issue(
                store,
                user_id=str(grant.user_id),
                client_id=row.client_id,
                grant_id=grant.grant_id,
                scopes=requested,
                resource=row.resource,
            )

    # access tokens

    async def load_access_token(self, token: str) -> AccessToken | None:
        claims = tokens.decode_access_token(token)
        if claims is None:
            return None

        with self._session_factory() as session:
            store = OAuthStore(session)
            if store.get_grant(claims.gid) is None:
                return None

            store.touch_grant(claims.gid)

        return AccessToken(
            token=token,
            client_id=claims.cid,
            scopes=claims.scope,
            expires_at=claims.exp,
            resource=claims.aud,
            subject=claims.sub,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self._session_factory() as session:
            store = OAuthStore(session)
            if isinstance(token, AccessToken):
                claims = tokens.decode_access_token(token.token)
                if claims is not None:
                    store.revoke_grant_by_id(claims.gid)
            else:
                row = store.consume_refresh_token(token.token)
                if row is not None:
                    store.revoke_grant_by_id(row.grant_id)


@lru_cache(maxsize=1)
def get_provider() -> MealieOAuthProvider:
    return MealieOAuthProvider()
