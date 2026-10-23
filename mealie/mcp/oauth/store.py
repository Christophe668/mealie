from datetime import datetime

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from mealie.db.models._model_base import SqlAlchemyBase
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

    def _save[T: SqlAlchemyBase](self, row: T) -> T:
        self.session.add(row)
        self.session.commit()
        return row

    # clients

    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = self.session.scalars(select(McpOAuthClient).where(McpOAuthClient.client_id == client_id)).first()
        return OAuthClientInformationFull.model_validate(row.metadata_json) if row else None

    def save_client(self, info: OAuthClientInformationFull) -> None:
        if not info.client_id:
            raise ValueError("client_id is required")

        # the plaintext secret stays in metadata_json because the SDK compares it directly on token requests
        values = {
            "client_secret_hash": tokens.hash_token(info.client_secret) if info.client_secret else None,
            "client_name": info.client_name,
            "redirect_uris": [str(uri) for uri in info.redirect_uris or []],
            "metadata_json": info.model_dump(mode="json"),
        }
        row = self.session.scalars(select(McpOAuthClient).where(McpOAuthClient.client_id == info.client_id)).first()
        if row is None:
            self._save(McpOAuthClient(client_id=info.client_id, **values))
            return

        for key, value in values.items():
            setattr(row, key, value)
        self.session.commit()

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
        # conditional delete: only the caller that actually removes the row gets the data
        deleted = self.session.execute(
            delete(McpOAuthPendingAuth).where(McpOAuthPendingAuth.request_id == request_id)
        ).rowcount
        self.session.commit()
        return result if deleted else None

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

    def peek_code(self, code: str) -> McpOAuthCode | None:
        row = self.session.scalars(select(McpOAuthCode).where(McpOAuthCode.code == code)).first()
        return row if row and row.expires_at > _now() else None

    def pop_code(self, code: str) -> McpOAuthCode | None:
        row = self.session.scalars(select(McpOAuthCode).where(McpOAuthCode.code == code)).first()
        if row is None:
            return None

        expired = row.expires_at <= _now()
        self.session.expunge(row)
        # conditional delete: of concurrent callers only one removes the row
        deleted = self.session.execute(delete(McpOAuthCode).where(McpOAuthCode.code == code)).rowcount
        self.session.commit()
        return None if expired or not deleted else row

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

    def revoke_grant_by_id(self, grant_id: str) -> None:
        """Revokes a grant regardless of owner (the caller proved possession of one of its tokens)."""
        grant = self.get_grant(grant_id)
        if grant is not None:
            self._revoke(grant)

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

    def peek_refresh_token(self, raw: str) -> McpOAuthRefreshToken | None:
        """Read-only lookup of a refresh token that is still usable (unused and unexpired)."""
        row = self.session.scalars(
            select(McpOAuthRefreshToken).where(McpOAuthRefreshToken.token_hash == tokens.hash_token(raw))
        ).first()
        return row if row and row.used_at is None and row.expires_at > _now() else None

    def consume_refresh_token(self, raw: str) -> McpOAuthRefreshToken | None:
        token_hash = tokens.hash_token(raw)
        now = _now()
        # atomic claim: only one concurrent caller can flip used_at from NULL
        claimed = self.session.execute(
            update(McpOAuthRefreshToken)
            .where(
                McpOAuthRefreshToken.token_hash == token_hash,
                McpOAuthRefreshToken.used_at.is_(None),
                McpOAuthRefreshToken.expires_at > now,
            )
            .values(used_at=now)
        ).rowcount
        self.session.commit()

        row = self.session.scalars(
            select(McpOAuthRefreshToken).where(McpOAuthRefreshToken.token_hash == token_hash)
        ).first()
        if row is None:
            return None
        if claimed:
            return row

        if row.used_at is not None and row.expires_at > now:
            # reuse of a rotated token: assume theft and kill the whole family
            grant = self.get_grant(row.grant_id)
            if grant is not None:
                self._revoke(grant)
        return None

    # housekeeping

    def purge_expired(self) -> None:
        now = _now()
        for model in (McpOAuthPendingAuth, McpOAuthCode, McpOAuthRefreshToken):
            self.session.execute(delete(model).where(model.expires_at <= now))
        self.session.commit()
