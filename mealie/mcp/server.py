from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from pydantic import AnyHttpUrl

from mealie.core.config import get_app_settings
from mealie.mcp.oauth.provider import get_provider
from mealie.mcp.scopes import ALL_SCOPES

INSTRUCTIONS = (
    "This server gives access to the user's Mealie recipes, meal plans and shopping lists. "
    "Call get_household_context first to learn the household, its members and its preferences. "
    "Always confirm with the user before any write (creating or changing recipes, meal plans or shopping lists)."
)


class MealieTokenVerifier(TokenVerifier):
    """Accepts only MCP access tokens issued by the Mealie OAuth provider (never regular Mealie session tokens)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return await get_provider().load_access_token(token)


def base_url() -> str:
    return get_app_settings().BASE_URL.rstrip("/")


def build_auth_settings() -> AuthSettings:
    url = base_url()
    return AuthSettings(
        issuer_url=AnyHttpUrl(url),
        resource_server_url=AnyHttpUrl(f"{url}/mcp"),
        required_scopes=None,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=list(ALL_SCOPES),
            default_scopes=list(ALL_SCOPES),
        ),
        revocation_options=RevocationOptions(enabled=True),
        # the provider binds tokens to grants; audience checks are not enforced by the bearer middleware
        validate_token_resource=False,
    )


# in this SDK version auth and the token verifier are given to the server, not to streamable_http_app()
mcp_server = MCPServer(
    "Mealie",
    instructions=INSTRUCTIONS,
    auth=build_auth_settings(),
    token_verifier=MealieTokenVerifier(),
)
