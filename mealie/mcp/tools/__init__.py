"""MCP tools. Importing this package registers every tool on `mealie.mcp.server.mcp_server`."""

from collections.abc import Callable
from typing import Any

import anyio

from mealie.mcp.context import McpContext, mcp_context


async def run_in_context[T](impl: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Runs `impl(ctx, *args, **kwargs)` inside `mcp_context()` on a worker thread, so blocking DB work
    stays off the event loop (context variables such as the access token are copied to the thread)."""

    def run() -> T:
        with mcp_context() as ctx:
            return impl(ctx, *args, **kwargs)

    return await anyio.to_thread.run_sync(run)


__all__ = ["McpContext", "run_in_context"]

# Imported last: the tool modules use `run_in_context` above and `mcp_server` from mealie.mcp.server.
from . import household, recipes  # noqa: E402,F401
