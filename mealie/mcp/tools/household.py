from datetime import datetime
from typing import Any

from mealie.mcp.auth import require_scope
from mealie.mcp.context import McpContext
from mealie.mcp.server import mcp_server
from mealie.mcp.tools import run_in_context

DEFAULT_LOCALE = "en-US"


def get_household_context_impl(ctx: McpContext) -> dict[str, Any]:
    user = ctx.user
    group = ctx.repos.groups.get_one(user.group_id)
    household = ctx.repos.households.get_one(user.household_id)
    members = ctx.repos.users.multi_query({"household_id": user.household_id})

    return {
        "group": {
            "id": str(user.group_id),
            "name": group.name if group else user.group,
            "slug": group.slug if group else user.group_slug,
        },
        "household": {"id": str(user.household_id), "name": household.name if household else user.household},
        "members": [
            {"id": str(m.id), "full_name": m.full_name, "username": m.username}
            for m in sorted(members, key=lambda m: (m.full_name or "").lower())
        ],
        "user": {"id": str(user.id), "full_name": user.full_name},
        "first_day_of_week": household.preferences.first_day_of_week if household and household.preferences else 0,
        # Mealie keeps the UI language in the browser only; there is no server-side locale yet.
        "locale": DEFAULT_LOCALE,
        "today": datetime.now().astimezone().date().isoformat(),
        "scopes_granted": sorted(ctx.access.scopes),
        # Member profiles (diets, allergies, dislikes) arrive in phase 2.
        "preferences": {},
    }


@mcp_server.tool()
@require_scope("recipes:read")
async def get_household_context() -> dict[str, Any]:
    """Call this first in every conversation. Returns the user's group and household, the household
    members, today's date (server time), the first day of the week (0 = Sunday), the locale, the
    scopes this connection was granted and the household preferences."""
    return await run_in_context(get_household_context_impl)
