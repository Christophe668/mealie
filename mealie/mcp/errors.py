from mcp.server.mcpserver.exceptions import ToolError


class McpToolError(ToolError):
    """Raised inside a tool; the SDK turns it into an `isError` tool result carrying the message."""


def not_found(kind: str, key: str) -> McpToolError:
    return McpToolError(f"{kind} not found: {key}")


def forbidden_scope(scope: str) -> McpToolError:
    return McpToolError(f"missing required scope: {scope}")
