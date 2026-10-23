from urllib.parse import urlparse

from fastapi import HTTPException, status

from mealie.mcp.oauth.provider import get_provider
from mealie.mcp.oauth.store import OAuthStore
from mealie.mcp.schemas import (
    McpAuthorizeDecision,
    McpAuthorizeRedirect,
    McpAuthorizeRequestOut,
    McpConnectionOut,
)
from mealie.routes._base import BaseUserController, controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.response import SuccessResponse

router = UserAPIRouter(prefix="/users/mcp", tags=["Users: MCP Connections"])


@controller(router)
class UserMcpConnectionsController(BaseUserController):
    @property
    def store(self) -> OAuthStore:
        return OAuthStore(self.session)

    @router.get("/authorize/{request_id}", response_model=McpAuthorizeRequestOut)
    def get_authorize_request(self, request_id: str):
        """Describe a pending OAuth authorization request so the user can consent to it"""
        pending = self.store.peek_pending(request_id)
        if pending is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Authorization request not found or expired")

        client_id, params = pending
        client = self.store.get_client(client_id)
        return McpAuthorizeRequestOut(
            request_id=request_id,
            client_name=client.client_name if client else None,
            client_id=client_id,
            scopes=list(params.scopes or []),
            redirect_host=urlparse(str(params.redirect_uri)).netloc,
        )

    @router.post("/authorize", response_model=McpAuthorizeRedirect)
    def decide_authorize_request(self, decision: McpAuthorizeDecision):
        """Approve or deny a pending OAuth authorization request"""
        try:
            redirect_url = get_provider().complete_authorization(
                decision.request_id, str(self.user.id), decision.approve
            )
        except KeyError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Authorization request not found or expired") from e

        return McpAuthorizeRedirect(redirect_url=redirect_url)

    @router.get("/connections", response_model=list[McpConnectionOut])
    def list_connections(self):
        """List the current user's active MCP connections"""
        store = self.store
        names: dict[str, str | None] = {}
        out: list[McpConnectionOut] = []
        for grant in store.list_grants(self.user.id):
            if grant.client_id not in names:
                client = store.get_client(grant.client_id)
                names[grant.client_id] = client.client_name if client else None
            out.append(
                McpConnectionOut(
                    grant_id=grant.grant_id,
                    client_id=grant.client_id,
                    client_name=names[grant.client_id],
                    scopes=list(grant.scopes),
                    created_at=grant.created_at,
                    last_used_at=grant.last_used_at,
                )
            )
        return out

    @router.delete("/connections/{grant_id}", response_model=SuccessResponse)
    def revoke_connection(self, grant_id: str):
        """Revoke one of the current user's MCP connections"""
        if not self.store.revoke_grant(grant_id, self.user.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")

        return SuccessResponse.respond("Connection revoked")
