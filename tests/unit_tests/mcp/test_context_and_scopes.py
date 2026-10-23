import contextlib

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session

from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError


def _token(subject: str, scopes: list[str]) -> AccessToken:
    return AccessToken(token="t", client_id="c", scopes=scopes, subject=subject)


def test_context_scopes_repos_to_user_household(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user):
    monkeypatch.setattr(context, "get_access_token", lambda: _token(str(unique_user.user_id), ["recipes:read"]))
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))

    with context.mcp_context() as ctx:
        assert str(ctx.user.id) == str(unique_user.user_id)
        assert str(ctx.repos.household_id) == str(unique_user.household_id)
        assert str(ctx.repos.group_id) == str(unique_user.group_id)
        assert context.cross_household_repos(ctx).household_id is None


def test_context_without_token_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(context, "get_access_token", lambda: None)
    with pytest.raises(McpToolError, match="unauthenticated"):
        with context.mcp_context():
            pass


@pytest.mark.asyncio
async def test_require_scope_blocks_missing_scope(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "get_access_token", lambda: _token("u1", ["recipes:read"]))

    @auth.require_scope("mealplan:write")
    async def tool(x: int) -> int:
        return x

    with pytest.raises(McpToolError, match="mealplan:write"):
        await tool(1)


@pytest.mark.asyncio
async def test_require_scope_allows_present_scope(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "get_access_token", lambda: _token("u1", ["recipes:read"]))

    @auth.require_scope("recipes:read")
    async def tool(x: int) -> int:
        return x + 1

    @auth.require_scope("recipes:read")
    def sync_tool(x: int) -> int:
        return x + 2

    assert await tool(1) == 2
    assert sync_tool(1) == 3
    assert tool.__name__ == "tool"
