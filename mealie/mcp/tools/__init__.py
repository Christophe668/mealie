"""MCP tools. Importing this package registers every tool on `mealie.mcp.server.mcp_server`."""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, cast

import anyio

from mealie.mcp.context import McpContext, mcp_context


async def run_in_context[T](impl: Callable[..., T] | Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
    """Runs `impl(ctx, *args, **kwargs)` inside `mcp_context()` on a worker thread, so blocking DB work
    stays off the event loop (context variables such as the access token are copied to the thread).

    `impl` may be async (the recipe writer's ingredient parser is): it then runs to completion on its
    own event loop inside the worker thread, with the same session, rather than on the server's loop."""

    def run() -> T:
        with mcp_context() as ctx:
            if inspect.iscoroutinefunction(impl):
                return asyncio.run(impl(ctx, *args, **kwargs))
            return cast(T, impl(ctx, *args, **kwargs))

    return await anyio.to_thread.run_sync(run)


__all__ = ["McpContext", "run_in_context"]

# Imported last: the tool modules use `run_in_context` above and `mcp_server` from mealie.mcp.server.
from . import feedback, household, mealplan, pantry, recipe_write, recipes, shopping  # noqa: E402,F401
