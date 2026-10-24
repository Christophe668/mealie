from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mealie.db.models._model_base import BaseMixins, SqlAlchemyBase
from mealie.db.models._model_utils.datetime import NaiveDateTime
from mealie.db.models._model_utils.guid import GUID


class McpOAuthClient(SqlAlchemyBase, BaseMixins):
    """A dynamically registered OAuth client (RFC 7591)."""

    __tablename__ = "mcp_oauth_clients"

    client_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    client_secret_hash: Mapped[str | None] = mapped_column(String)
    client_name: Mapped[str | None] = mapped_column(String)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    # the full OAuthClientInformationFull.model_dump()
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    def __init__(
        self,
        client_id: str,
        redirect_uris: list[str],
        metadata_json: dict[str, Any],
        client_secret_hash: str | None = None,
        client_name: str | None = None,
        **_,
    ) -> None:
        self.client_id = client_id
        self.client_secret_hash = client_secret_hash
        self.client_name = client_name
        self.redirect_uris = redirect_uris
        self.metadata_json = metadata_json


class McpOAuthPendingAuth(SqlAlchemyBase, BaseMixins):
    """An authorization request waiting for the user to log in and consent."""

    __tablename__ = "mcp_oauth_pending_auths"

    request_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    # AuthorizationParams.model_dump(mode="json")
    params_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(NaiveDateTime, nullable=False)

    def __init__(self, request_id: str, client_id: str, params_json: dict[str, Any], expires_at: datetime, **_) -> None:
        self.request_id = request_id
        self.client_id = client_id
        self.params_json = params_json
        self.expires_at = expires_at


class McpOAuthCode(SqlAlchemyBase, BaseMixins):
    """A single-use authorization code issued after user consent."""

    __tablename__ = "mcp_oauth_codes"

    code: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String, nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String, nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resource: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(NaiveDateTime, nullable=False)

    def __init__(
        self,
        code: str,
        client_id: str,
        user_id: GUID,
        scopes: list[str],
        code_challenge: str,
        redirect_uri: str,
        redirect_uri_provided_explicitly: bool,
        expires_at: datetime,
        resource: str | None = None,
        **_,
    ) -> None:
        self.code = code
        self.client_id = client_id
        self.user_id = user_id
        self.scopes = scopes
        self.code_challenge = code_challenge
        self.redirect_uri = redirect_uri
        self.redirect_uri_provided_explicitly = redirect_uri_provided_explicitly
        self.resource = resource
        self.expires_at = expires_at


class McpOAuthGrant(SqlAlchemyBase, BaseMixins):
    """A user's consent for a client; refresh tokens of one grant form a rotation family."""

    __tablename__ = "mcp_oauth_grants"

    grant_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(NaiveDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(NaiveDateTime)

    def __init__(
        self,
        grant_id: str,
        user_id: GUID,
        client_id: str,
        scopes: list[str],
        last_used_at: datetime | None = None,
        revoked_at: datetime | None = None,
        **_,
    ) -> None:
        self.grant_id = grant_id
        self.user_id = user_id
        self.client_id = client_id
        self.scopes = scopes
        self.last_used_at = last_used_at
        self.revoked_at = revoked_at


class McpOAuthRefreshToken(SqlAlchemyBase, BaseMixins):
    """A rotating refresh token, stored only as a hash."""

    __tablename__ = "mcp_oauth_refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    grant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resource: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(NaiveDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(NaiveDateTime)

    def __init__(
        self,
        token_hash: str,
        grant_id: str,
        client_id: str,
        scopes: list[str],
        expires_at: datetime,
        resource: str | None = None,
        used_at: datetime | None = None,
        **_,
    ) -> None:
        self.token_hash = token_hash
        self.grant_id = grant_id
        self.client_id = client_id
        self.scopes = scopes
        self.resource = resource
        self.expires_at = expires_at
        self.used_at = used_at
