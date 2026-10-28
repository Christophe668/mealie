from typing import Any
from uuid import UUID

from mealie.mcp.errors import McpToolError


def check_keys(entry: Any, allowed: frozenset[str], where: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise McpToolError(f"{where}: expected an object")
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise McpToolError(f"{where}: unknown key(s) {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}")
    return dict(entry)


def parse_uuid(where: str, name: str, value: Any) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as e:
        raise McpToolError(f"{where}: {name} is not a valid id: {value!r}") from e
