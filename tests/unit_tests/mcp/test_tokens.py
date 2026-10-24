from datetime import timedelta

import mealie.mcp.oauth.tokens as tokens
from mealie.core.security.tokens import create_access_token
from mealie.mcp.oauth.tokens import decode_access_token, hash_token, issue_access_token, new_opaque_token


def _issue(scopes: list[str] | None = None, resource: str | None = "http://x/mcp") -> tuple[str, int]:
    return issue_access_token(
        user_id="u", client_id="c", grant_id="g", scopes=scopes or ["recipes:read"], resource=resource
    )


def test_issue_and_decode_roundtrip():
    tok, exp = _issue()
    claims = decode_access_token(tok)
    assert claims
    assert claims.sub == "u"
    assert claims.cid == "c"
    assert claims.gid == "g"
    assert claims.scope == ["recipes:read"]
    assert claims.aud == "http://x/mcp"
    assert claims.exp == exp


def test_roundtrip_multiple_scopes_and_no_resource():
    tok, _ = _issue(scopes=["recipes:read", "recipes:write"], resource=None)
    claims = decode_access_token(tok)
    assert claims
    assert claims.scope == ["recipes:read", "recipes:write"]
    assert claims.aud is None


def test_decode_rejects_session_token():
    tok, _ = create_access_token({"sub": "u"})
    assert decode_access_token(tok) is None


def test_decode_rejects_expired(monkeypatch):
    monkeypatch.setattr(tokens, "ACCESS_TOKEN_TTL", timedelta(seconds=-1))
    assert decode_access_token(_issue()[0]) is None


def test_decode_rejects_garbage_and_tampered():
    assert decode_access_token("not-a-jwt") is None
    tok, _ = _issue()
    assert decode_access_token(tok[:-2] + "xx") is None


def test_hash_token_is_stable_and_not_identity():
    raw = new_opaque_token()
    assert hash_token(raw) == hash_token(raw)
    assert hash_token(raw) != raw
    assert new_opaque_token() != raw
