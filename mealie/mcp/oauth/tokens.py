import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel, ValidationError

from mealie.core.config import get_app_settings
from mealie.core.security.tokens import ALGORITHM, ISS

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=90)
AUTH_CODE_TTL = timedelta(minutes=10)
PENDING_AUTH_TTL = timedelta(minutes=10)


class McpTokenClaims(BaseModel):
    sub: str
    cid: str
    gid: str
    scope: list[str]
    aud: str | None = None
    exp: int
    iat: int
    jti: str


def issue_access_token(
    *, user_id: str, client_id: str, grant_id: str, scopes: list[str], resource: str | None
) -> tuple[str, int]:
    """Signs an MCP access token, returning it alongside its expiry as epoch seconds."""
    issued_at = datetime.now(UTC)
    expires_at = int((issued_at + ACCESS_TOKEN_TTL).timestamp())

    payload: dict = {
        "mcp": True,
        "iss": ISS,
        "sub": user_id,
        "cid": client_id,
        "gid": grant_id,
        "scope": " ".join(scopes),
        "iat": int(issued_at.timestamp()),
        "exp": expires_at,
        "jti": secrets.token_urlsafe(16),
    }
    if resource is not None:
        payload["aud"] = resource

    return jwt.encode(payload, get_app_settings().SECRET, algorithm=ALGORITHM), expires_at


def decode_access_token(token: str) -> McpTokenClaims | None:
    """Returns the claims of a valid MCP access token, or None for anything else (never raises)."""
    try:
        payload = jwt.decode(
            token,
            get_app_settings().SECRET,
            algorithms=[ALGORITHM],
            issuer=ISS,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        return None

    if not payload.get("mcp"):
        return None

    try:
        return McpTokenClaims(**{**payload, "scope": str(payload.get("scope", "")).split()})
    except ValidationError:
        return None


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
