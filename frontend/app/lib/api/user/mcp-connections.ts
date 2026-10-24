import { BaseAPI } from "../base/base-clients";

// Mirrors mealie/mcp/schemas.py. Those models live outside mealie/schema, so `task dev:generate`
// does not emit TypeScript types for them.
export interface McpAuthorizeRequest {
  requestId: string;
  clientName: string | null;
  clientId: string;
  scopes: string[];
  redirectHost: string;
}

export interface McpAuthorizeRedirect {
  redirectUrl: string;
}

export interface McpConnection {
  grantId: string;
  clientId: string;
  clientName: string | null;
  scopes: string[];
  createdAt: string;
  lastUsedAt: string | null;
}

/** i18n key for each OAuth scope the server can grant (see mealie/mcp/scopes.py). */
export const MCP_SCOPE_I18N_KEYS: Record<string, string> = {
  "recipes:read": "settings.mcp.scope.recipes-read",
  "recipes:write": "settings.mcp.scope.recipes-write",
  "mealplan:write": "settings.mcp.scope.mealplan-write",
  "shopping:write": "settings.mcp.scope.shopping-write",
  "household:write": "settings.mcp.scope.household-write",
  "pantry:write": "settings.mcp.scope.pantry-write",
};

const prefix = "/api/users/mcp";

const routes = {
  authorize: `${prefix}/authorize`,
  authorizeRequestId: (requestId: string) => `${prefix}/authorize/${encodeURIComponent(requestId)}`,
  connections: `${prefix}/connections`,
  connectionsGrantId: (grantId: string) => `${prefix}/connections/${encodeURIComponent(grantId)}`,
};

export class McpConnectionsApi extends BaseAPI {
  async getAuthorizeRequest(requestId: string) {
    return await this.requests.get<McpAuthorizeRequest>(routes.authorizeRequestId(requestId));
  }

  async decide(requestId: string, approve: boolean) {
    return await this.requests.post<McpAuthorizeRedirect>(routes.authorize, { requestId, approve });
  }

  async getConnections() {
    return await this.requests.get<McpConnection[]>(routes.connections);
  }

  async revoke(grantId: string) {
    return await this.requests.delete<{ message: string }>(routes.connectionsGrantId(grantId));
  }
}
