from fastapi.testclient import TestClient

from mealie.mcp.oauth.tokens import issue_access_token
from mealie.mcp.scopes import ALL_SCOPES
from tests.utils import api_routes
from tests.utils.fixture_schemas import TestUser


def _mcp_token(user: TestUser) -> str:
    tok, _ = issue_access_token(
        user_id=str(user.user_id),
        client_id="c",
        grant_id="g",
        scopes=list(ALL_SCOPES),
        resource=None,
    )
    return tok


def test_mcp_token_rejected_on_api(api_client: TestClient, unique_user: TestUser):
    tok = _mcp_token(unique_user)

    r = api_client.get(api_routes.users_self, headers={"Authorization": f"Bearer {tok}"})

    assert r.status_code == 401


def test_regular_token_still_accepted_on_api(api_client: TestClient, unique_user: TestUser):
    r = api_client.get(api_routes.users_self, headers=unique_user.token)

    assert r.status_code == 200
