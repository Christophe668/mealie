from datetime import datetime

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mealie.db.models._model_utils.datetime import get_utc_now
from mealie.db.models._model_utils.guid import GUID
from mealie.db.models.mcp.oauth import (
    McpOAuthClient,
    McpOAuthCode,
    McpOAuthGrant,
    McpOAuthPendingAuth,
    McpOAuthRefreshToken,
)
from mealie.mcp.oauth import tokens


def _now() -> datetime:
    """UTC-aware, as NaiveDateTime columns return aware values and strip tzinfo on write."""
    return get_utc_now()


class OAuthStore:
    """Persistence for the MCP OAuth provider. Every write is committed immediately."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _save(self, row: McpOAuthClient | McpOAuthPendingAuth | McpOAuthCode | McpOAuthGrant | McpOAuthRefreshToken):
        self.session.add(row)
        self.session.commit()
        return row

    def _delete_row(self, row) -> None:
        self.session.delete(row)
        self.session.commit()

    # clients

    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = self.session.scalars(select(McpOAuthClient).where(McpOAuthClient.client_id == client_id)).first()
        return OAuthClientInformationFull.model_validate(row.metadata_json) if row else None

    def save_client(self, info: OAuthClientInformationFull) -> None:
        if not info.client_id:
            raise ValueError("client_id is required")

        self._save(
            McpOAuthClient(
                client_id=info.client_id,
                client_secret_hash=tokens.hash_token(info.client_secret) if info.client_secret else None,
                client_name=info.client_name,
                redirect_uris=[str(uri) for uri in info.redirect_uris or []],
                metadata_json=info.model_dump(mode="json"),
            )
        )

    # pending authorizations

    def create_pending(self, client_id: str, params: AuthorizationParams) -> str:
        request_id = tokens.new_opaque_token()
        self._save(
            McpOAuthPendingAuth(
                request_id=request_id,
                client_id=client_id,
                params_json=params.model_dump(mode="json"),
                expires_at=_now() + tokens.PENDING_AUTH_TTL,
            )
        )
        return request_id

    def _live_pending(self, request_id: str) -> McpOAuthPendingAuth | None:
        row = self.session.scalars(
            select(McpOAuthPendingAuth).where(McpOAuthPendingAuth.request_id == request_id)
        ).first()
        return row if row and row.expires_at > _now() else None

    def peek_pending(self, request_id: str) -> tuple[str, AuthorizationParams] | None:
        row = self._live_pending(request_id)
        return (row.client_id, AuthorizationParams.model_validate(row.params_json)) if row else None

    def pop_pending(self, request_id: str) -> tuple[str, AuthorizationParams] | None:
        row = self._live_pending(request_id)
        if row is None:
            return None

        result = (row.client_id, AuthorizationParams.model_validate(row.params_json))
        self._delete_row(row)
        return result

    # authorization codes

    def create_code(self, *, client_id: str, user_id: GUID, params: AuthorizationParams) -> str:
        code = tokens.new_opaque_token()
        self._save(
            McpOAuthCode(
                code=code,
                client_id=client_id,
                user_id=user_id,
                scopes=list(params.scopes or []),
                code_challenge=params.code_challenge,
                redirect_uri=str(params.redirect_uri),
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=params.resource,
                expires_at=_now() + tokens.AUTH_CODE_TTL,
            )
        )
        return code

    def pop_code(self, code: str) -> McpOAuthCode | None:
        row = self.session.scalars(select(McpOAuthCode).where(McpOAuthCode.code == code)).first()
        if row is None:
            return None

        expired = row.expires_at <= _now()
        self._delete_row(row)
        return None if expired else row

    # grants

    def create_grant(self, *, user_id: GUID, client_id: str, scopes: list[str]) -> McpOAuthGrant:
        grant = McpOAuthGrant(
            grant_id=tokens.new_opaque_token(), user_id=user_id, client_id=client_id, scopes=list(scopes)
        )
        return self._save(grant)

    def get_grant(self, grant_id: str) -> McpOAuthGrant | None:
        return self.session.scalars(
            select(McpOAuthGrant).where(McpOAuthGrant.grant_id == grant_id, McpOAuthGrant.revoked_at.is_(None))
        ).first()

    def list_grants(self, user_id: GUID) -> list[McpOAuthGrant]:
        return list(
            self.session.scalars(
                select(McpOAuthGrant)
                .where(McpOAuthGrant.user_id == user_id, McpOAuthGrant.revoked_at.is_(None))
                .order_by(McpOAuthGrant.created_at)
            )
        )

    def revoke_grant(self, grant_id: str, user_id: GUID) -> bool:
        grant = self.get_grant(grant_id)
        if grant is None or grant.user_id != user_id:
            return False

        self._revoke(grant)
        return True

    def touch_grant(self, grant_id: str) -> None:
        grant = self.get_grant(grant_id)
        if grant is not None:
            grant.last_used_at = _now()
            self.session.commit()

    def _revoke(self, grant: McpOAuthGrant) -> None:
        grant.revoked_at = _now()
        self.session.execute(delete(McpOAuthRefreshToken).where(McpOAuthRefreshToken.grant_id == grant.grant_id))
        self.session.commit()

    # refresh tokens

    def create_refresh_token(self, *, grant_id: str, client_id: str, scopes: list[str], resource: str | None) -> str:
        raw = tokens.new_opaque_token()
        self._save(
            McpOAuthRefreshToken(
                token_hash=tokens.hash_token(raw),
                grant_id=grant_id,
                client_id=client_id,
                scopes=list(scopes),
                resource=resource,
                expires_at=_now() + tokens.REFRESH_TOKEN_TTL,
            )
        )
        return raw

    def consume_refresh_token(self, raw: str) -> McpOAuthRefreshToken | None:
        row = self.session.scalars(
            select(McpOAuthRefreshToken).where(McpOAuthRefreshToken.token_hash == tokens.hash_token(raw))
        ).first()
        if row is None or row.expires_at <= _now():
            return None

        if row.used_at is not None:
            # reuse of a rotated token: assume theft and kill the whole family
            grant = self.get_grant(row.grant_id)
            if grant is not None:
                self._revoke(grant)
            return None

        row.used_at = _now()
        self.session.commit()
        return row

    # housekeeping

    def purge_expired(self) -> None:
        now = _now()
        for model in (McpOAuthPendingAuth, McpOAuthCode, McpOAuthRefreshToken):
            self.session.execute(delete(model).where(model.expires_at <= now))
        self.session.commit()
