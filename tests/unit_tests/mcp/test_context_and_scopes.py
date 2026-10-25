import contextlib
import inspect
import logging
import re
from uuid import uuid4

import pytest
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session

from mealie.mcp import auth, context
from mealie.mcp.errors import McpToolError
from tests.utils.factories import random_string


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


def _patch_ctx(monkeypatch: pytest.MonkeyPatch, session: Session, subject: str) -> None:
    monkeypatch.setattr(context, "get_access_token", lambda: _token(subject, ["recipes:read"]))
    monkeypatch.setattr(context, "session_factory", lambda: contextlib.nullcontext(session))


def _tag_exists(session: Session, name: str) -> bool:
    from mealie.db.models.recipe.tag import Tag

    session.expire_all()
    return session.query(Tag).filter(Tag.name == name).first() is not None


def test_context_commits_on_clean_exit(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user):
    from mealie.schema.recipe.recipe_category import TagSave

    _patch_ctx(monkeypatch, session, str(unique_user.user_id))
    name = random_string()
    with context.mcp_context() as ctx:
        ctx.session.add(
            ctx.repos.tags.model(**TagSave(name=name, slug=name, group_id=unique_user.group_id).model_dump())
        )
        ctx.session.flush()
    session.rollback()
    assert _tag_exists(session, name)


def test_context_rolls_back_on_exception(monkeypatch: pytest.MonkeyPatch, session: Session, unique_user):
    from mealie.schema.recipe.recipe_category import TagSave

    _patch_ctx(monkeypatch, session, str(unique_user.user_id))
    name = random_string()
    with pytest.raises(RuntimeError, match="boom"):
        with context.mcp_context() as ctx:
            ctx.session.add(
                ctx.repos.tags.model(**TagSave(name=name, slug=name, group_id=unique_user.group_id).model_dump())
            )
            ctx.session.flush()
            raise RuntimeError("boom")
    assert not _tag_exists(session, name)


def test_context_unknown_user_raises(monkeypatch: pytest.MonkeyPatch, session: Session):
    _patch_ctx(monkeypatch, session, str(uuid4()))
    with pytest.raises(McpToolError, match="unknown user"):
        with context.mcp_context():
            pass


def test_context_malformed_subject_is_unauthenticated(monkeypatch: pytest.MonkeyPatch, session: Session):
    _patch_ctx(monkeypatch, session, "not-a-uuid")
    with pytest.raises(McpToolError, match="unauthenticated"):
        with context.mcp_context():
            pass


def test_require_scope_preserves_signature():
    async def original(a: int, b: str = "x") -> dict[str, int]:
        return {}

    decorated = auth.require_scope("recipes:read")(original)
    assert inspect.signature(decorated) == inspect.signature(original)
    assert decorated.__annotations__ == original.__annotations__


@pytest.mark.asyncio
async def test_require_scope_logging(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setattr(auth, "get_access_token", lambda: _token("user-42", ["recipes:read"]))
    secret = "distinctive-secret-arg"

    @auth.require_scope("recipes:read")
    async def good(q: str) -> str:
        return "result-" + q

    @auth.require_scope("mealplan:write")
    async def bad(q: str) -> str:
        return q

    with caplog.at_level(logging.INFO, logger="mcp"):
        await good(secret)
        with pytest.raises(McpToolError):
            await bad(secret)

    msgs = [r.getMessage() for r in caplog.records if r.name == "mcp"]
    assert len(msgs) == 2
    assert re.fullmatch(r"tool=good user=user-42 ms=\d+ ok=True", msgs[0])
    assert re.fullmatch(r"tool=bad user=user-42 ms=\d+ ok=False", msgs[1])
    assert all(secret not in m for m in msgs)


@pytest.mark.asyncio
async def test_require_scope_logs_the_given_tool_name(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(auth, "get_access_token", lambda: _token("user-42", ["recipes:write"]))

    async def _inner() -> int:
        return 1

    tool = auth.require_scope("recipes:write", name="update_recipe")(_inner)
    with caplog.at_level(logging.INFO, logger="mcp"):
        await tool()

    msgs = [r.getMessage() for r in caplog.records if r.name == "mcp"]
    assert len(msgs) == 1
    assert re.fullmatch(r"tool=update_recipe user=user-42 ms=\d+ ok=True", msgs[0])


def test_require_scope_sync_deny_and_no_token(monkeypatch: pytest.MonkeyPatch):
    @auth.require_scope("mealplan:write")
    def tool() -> int:
        return 1

    monkeypatch.setattr(auth, "get_access_token", lambda: _token("u1", ["recipes:read"]))
    with pytest.raises(McpToolError, match="mealplan:write"):
        tool()

    monkeypatch.setattr(auth, "get_access_token", lambda: None)
    with pytest.raises(McpToolError, match="missing required scope"):
        tool()
