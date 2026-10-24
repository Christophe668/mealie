"""Fork-owned: group-wide lists must not filter or sort on another household's pantry or feedback.

Kept out of upstream's `test_group_self_service.py` to keep the merge surface small.
"""

import pytest
from fastapi.testclient import TestClient

from mealie.schema.household.pantry import PantryItemCreate
from mealie.services.claude_context.pantry_service import PantryService
from tests.utils import api_routes, random_string
from tests.utils.fixture_schemas import TestUser


@pytest.mark.parametrize(
    "route, params",
    [
        (api_routes.groups_households, {"queryFilter": 'pantry_items.name = "{secret}"'}),
        (api_routes.groups_households, {"queryFilter": 'recipe_feedback.created_at > "2000-01-01"'}),
        (api_routes.groups_households, {"orderBy": "pantry_items.name"}),
        (api_routes.groups_members, {"queryFilter": 'household.pantry_items.name = "{secret}"'}),
        (api_routes.groups_members, {"queryFilter": 'household.recipe_feedback.created_at > "2000-01-01"'}),
        (api_routes.recipes, {"queryFilter": 'user.household.pantry_items.name = "{secret}"'}),
        (api_routes.recipes, {"orderBy": "user.household.recipe_feedback.created_at"}),
    ],
)
def test_group_wide_lists_cannot_filter_on_another_households_pantry_or_feedback(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, route: str, params: dict[str, str]
):
    secret = random_string()
    PantryService(h2_user.repos).add_item(PantryItemCreate(name=secret))

    response = api_client.get(
        route, params={k: v.format(secret=secret) for k, v in params.items()}, headers=unique_user.token
    )
    assert response.status_code == 400
