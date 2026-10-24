from fastapi.testclient import TestClient

from tests.utils import api_routes


def test_app_theme_defaults_to_design_palette(api_client: TestClient):
    response = api_client.get(api_routes.app_about_theme)
    assert response.status_code == 200

    theme = response.json()
    assert theme["lightPrimary"] == "#F2B01E"
    assert theme["lightAccent"] == "#17201B"
    assert theme["lightSecondary"] == "#5B655F"
    assert theme["lightSuccess"] == "#489B4B"
    assert theme["darkPrimary"] == "#F2B01E"
    assert theme["darkAccent"] == "#ECEEEA"
    assert theme["darkSecondary"] == "#9AA49E"
    assert theme["darkError"] == "#E75B58"
