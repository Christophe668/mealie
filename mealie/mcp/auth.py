import functools
import inspect
import time
from collections.abc import Callable
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

from mealie.core.root_logger import get_logger

from .errors import forbidden_scope

logger = get_logger("mcp")


def _subject() -> str:
    access = get_access_token()
    return (access.subject if access else None) or "-"


def _check(scope: str) -> None:
    access = get_access_token()
    if access is None or scope not in access.scopes:
        raise forbidden_scope(scope)


def _log(name: str, user: str, started: float, ok: bool) -> None:
    logger.info("tool=%s user=%s ms=%d ok=%s", name, user, int((time.monotonic() - started) * 1000), ok)


def require_scope(scope: str, name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Reject the call unless the access token carries `scope`; also logs one line per call (no arguments/results).

    The log line names the tool `name`, defaulting to the function's own name."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                started, user, ok = time.monotonic(), _subject(), False
                try:
                    _check(scope)
                    result = await fn(*args, **kwargs)
                    ok = True
                    return result
                finally:
                    _log(tool_name, user, started, ok)

            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started, user, ok = time.monotonic(), _subject(), False
            try:
                _check(scope)
                result = fn(*args, **kwargs)
                ok = True
                return result
            finally:
                _log(tool_name, user, started, ok)

        return wrapper

    return decorator
