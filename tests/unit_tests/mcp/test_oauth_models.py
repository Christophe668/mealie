from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealie.db.models.mcp.oauth import (
    McpOAuthClient,
    McpOAuthCode,
    McpOAuthGrant,
    McpOAuthPendingAuth,
    McpOAuthRefreshToken,
)
from mealie.db.models.users import User
from tests.utils.factories import random_string

CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=10)


def test_oauth_client_roundtrip(session: Session):
    client_id = random_string()
    session.add(
        McpOAuthClient(
            client_id=client_id,
            client_name="Claude",
            redirect_uris=[CALLBACK],
            metadata_json={"client_id": client_id},
        )
    )
    session.commit()

    row = session.query(McpOAuthClient).filter_by(client_id=client_id).one()
    assert row.redirect_uris == [CALLBACK]
    assert row.metadata_json == {"client_id": client_id}
    assert row.client_secret_hash is None
    assert row.created_at is not None


def test_oauth_client_id_is_unique(session: Session):
    client_id = random_string()
    session.add(McpOAuthClient(client_id=client_id, redirect_uris=[], metadata_json={}))
    session.commit()

    session.add(McpOAuthClient(client_id=client_id, redirect_uris=[], metadata_json={}))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_pending_auth_roundtrip(session: Session):
    request_id = random_string()
    expires_at = _future()
    session.add(
        McpOAuthPendingAuth(
            request_id=request_id,
            client_id="c1",
            params_json={"state": "abc", "scopes": ["recipes:read"]},
            expires_at=expires_at,
        )
    )
    session.commit()

    row = session.query(McpOAuthPendingAuth).filter_by(request_id=request_id).one()
    assert row.params_json == {"state": "abc", "scopes": ["recipes:read"]}
    assert row.expires_at.replace(tzinfo=None) == expires_at.replace(tzinfo=None)


def test_code_roundtrip(session: Session, unique_user):
    code = random_string()
    session.add(
        McpOAuthCode(
            code=code,
            client_id="c1",
            user_id=unique_user.user_id,
            scopes=["recipes:read"],
            code_challenge="challenge",
            redirect_uri=CALLBACK,
            redirect_uri_provided_explicitly=True,
            expires_at=_future(),
        )
    )
    session.commit()

    row = session.query(McpOAuthCode).filter_by(code=code).one()
    assert row.user_id == unique_user.user_id
    assert row.scopes == ["recipes:read"]
    assert row.redirect_uri_provided_explicitly is True
    assert row.resource is None


def test_grant_defaults(session: Session, unique_user):
    grant_id = random_string()
    grant = McpOAuthGrant(grant_id=grant_id, user_id=unique_user.user_id, client_id="c1", scopes=["recipes:read"])
    session.add(grant)
    session.commit()

    assert grant.revoked_at is None
    assert grant.last_used_at is None
    assert grant.scopes == ["recipes:read"]


def test_refresh_token_roundtrip(session: Session):
    token_hash = random_string()
    session.add(
        McpOAuthRefreshToken(
            token_hash=token_hash,
            grant_id="g1",
            client_id="c1",
            scopes=["recipes:read"],
            resource="https://mealie.example/mcp",
            expires_at=_future(),
        )
    )
    session.commit()

    row = session.query(McpOAuthRefreshToken).filter_by(token_hash=token_hash).one()
    assert row.used_at is None
    assert row.resource == "https://mealie.example/mcp"
    assert row.scopes == ["recipes:read"]


def test_deleting_user_cascades_to_codes_and_grants(session: Session, unique_user_fn_scoped):
    user_id = unique_user_fn_scoped.user_id
    code, grant_id = random_string(), random_string()
    session.add(
        McpOAuthCode(
            code=code,
            client_id="c1",
            user_id=user_id,
            scopes=[],
            code_challenge="challenge",
            redirect_uri=CALLBACK,
            redirect_uri_provided_explicitly=True,
            expires_at=_future(),
        )
    )
    session.add(McpOAuthGrant(grant_id=grant_id, user_id=user_id, client_id="c1", scopes=[]))
    session.commit()

    # SQLite does not enforce foreign keys unless asked to; Postgres always does
    session.execute(text("PRAGMA foreign_keys=ON"))
    try:
        session.execute(delete(User).where(User.id == user_id))
        session.commit()
    finally:
        session.execute(text("PRAGMA foreign_keys=OFF"))

    assert session.query(McpOAuthCode).filter_by(code=code).count() == 0
    assert session.query(McpOAuthGrant).filter_by(grant_id=grant_id).count() == 0
