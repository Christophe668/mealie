from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from sqlalchemy.orm import Session

from mealie.db.db_setup import session_context
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.user.user import PrivateUser

from .errors import McpToolError

# Indirection so tests can swap the session source.
session_factory = session_context


@dataclass
class McpContext:
    user: PrivateUser
    repos: AllRepositories
    session: Session
    access: AccessToken


@contextmanager
def mcp_context() -> Iterator[McpContext]:
    access = get_access_token()
    if access is None or not access.subject:
        raise McpToolError("unauthenticated")

    with session_factory() as session:
        try:
            user = get_repositories(session, group_id=None, household_id=None).users.get_one(
                access.subject, "id", any_case=False
            )
            # Avoid lazy loads on user relationships holding locks (see get_current_user).
            session.commit()
            if user is None:
                raise McpToolError("unknown user")

            repos = get_repositories(session, group_id=user.group_id, household_id=user.household_id)
            yield McpContext(user=user, repos=repos, session=session, access=access)
            session.commit()
        except BaseException:
            session.rollback()
            raise


def cross_household_repos(ctx: McpContext) -> AllRepositories:
    """Group-wide repositories (all households), for group-wide recipe search."""
    return get_repositories(ctx.session, group_id=ctx.user.group_id, household_id=None)
