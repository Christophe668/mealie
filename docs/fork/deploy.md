# Deploying the fork and connecting claude.ai

This fork exposes an OAuth 2.1-protected MCP server at `https://<your-domain>/mcp`. claude.ai connects to it as a custom connector.

## Prerequisites

- A domain name pointing at your host (or a Cloudflare Tunnel hostname).
- HTTPS in front of Mealie. claude.ai only talks to public HTTPS endpoints.
- Docker with Compose v2.

> **`BASE_URL` must start with `https://`** (or point at `localhost`/`127.0.0.1` for local tests). With a plain `http://` LAN URL, Mealie logs a WARNING and does **not** register the MCP/OAuth routes. The container healthcheck only probes the MCP metadata when `BASE_URL` qualifies.

## Run the stack

```bash
cp .env.example .env
# edit .env: set BASE_URL=https://mealie.example.com and change the passwords
docker compose up -d
```

The compose file pulls `ghcr.io/christophe668/mealie:main` (built by `.github/workflows/fork-image.yml` on every push to `main`). To build locally instead: `docker compose up -d --build`.

Mealie listens on host port `9925`. Signup is disabled from the start (`ALLOW_SIGNUP=false`). Log in with Mealie's default admin (`changeme@example.com` / `MyPassword`) and change both immediately.

## Reverse proxy

### Caddy

```caddyfile
mealie.example.com {
    reverse_proxy localhost:9925
}
```

### Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:9925
# or, for a named tunnel routed to mealie.example.com:
cloudflared tunnel run --url http://localhost:9925 <tunnel-name>
```

## Rate limiting and workers

- Set `HOST_IP` in `.env` to your reverse proxy's IP (instead of the default `*`) so per-IP rate limiting sees the real client address and cannot be spoofed via forwarded headers.
- The MCP transport is stateless, so running multiple workers (`UVICORN_WORKERS`) is fine. Note that the rate limiter is per process, so limits apply per worker.

## Add to claude.ai

1. Open claude.ai, Settings, Connectors.
2. Choose **Add custom connector**.
3. Enter the URL `https://<domain>/mcp`.
4. You are redirected to Mealie: sign in and approve access.
5. The connector's tools are now available in conversations.

The pantry tools need the `pantry:write` permission. A connection made before it existed does not have it: disconnect and reconnect the connector to grant it.

## Pantry and freshness

Each household has a pantry (Household, Pantry): what you have, where it is (fridge, freezer, cupboard, other), when it was bought and opened, and an optional "use by" date. On the shopping list, **Put away** moves the bought items into the pantry with today's date. A food that is in the pantry counts as "on hand", so shopping lists built from the meal plan skip it.

Mealie only stores the dates. Claude estimates whether something is still good from those dates and general food knowledge, and gives that as guidance, never as food safety advice. Claude reads the pantry with the `recipes:read` scope; changing it (`update_pantry`, `put_away_shopping_items`) needs `pantry:write`, shown as "Manage the pantry" on the consent page.

## Verify

```bash
curl https://<domain>/.well-known/oauth-authorization-server
curl https://<domain>/.well-known/oauth-protected-resource/mcp
# unauthenticated MCP calls must be rejected with 401 and a WWW-Authenticate header
curl -i -X POST https://<domain>/mcp
```

The protected-resource document should report `"resource": "https://<domain>/mcp"`.
