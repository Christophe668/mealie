from mealie.core import root_logger
from mealie.db.db_setup import session_context
from mealie.mcp.oauth.store import OAuthStore

logger = root_logger.get_logger()


def purge_expired_mcp_oauth() -> None:
    """Daily scheduler task: removes expired or spent MCP OAuth rows (see `OAuthStore.purge_expired`)."""
    logger.debug("purging expired mcp oauth rows")
    with session_context() as session:
        OAuthStore(session).purge_expired()
    logger.info("expired mcp oauth rows purged")
