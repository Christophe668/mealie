# Deploying the fork and connecting claude.ai

This fork exposes an OAuth 2.1-protected MCP server at `https://<your-domain>/mcp`. claude.ai connects to it as a custom connector.

Running on a NAS (Synology, QNAP, Unraid, TrueNAS)? Follow [nas.md](nas.md) instead: one compose project with a Cloudflare Tunnel, no port forwarding.

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

The connector offers these tools, each behind the permission in brackets:

- Recipes: `search_recipes`, `get_recipe` (`recipes:read`); `create_recipe`, `update_recipe`, `import_recipe_from_url`, `set_recipe_image` (`recipes:write`).
- Meal plan: `get_mealplan`, `get_recent_meals` (`recipes:read`); `add_mealplan_entries`, `remove_mealplan_entry` (`mealplan:write`).
- Shopping: `get_shopping_list` (`recipes:read`); `create_shopping_list_from_mealplan`, `add_shopping_items`, `check_shopping_items` (`shopping:write`).
- Pantry: `get_pantry` (`recipes:read`); `update_pantry`, `put_away_shopping_items` (`pantry:write`).
- Feedback: `get_recipe_feedback` (`recipes:read`); `record_recipe_feedback` (`recipes:write`).
- Household: `get_household_context` (`recipes:read`); `update_household_profile` (`household:write`).

Reading the pantry (`get_pantry`) needs only `recipes:read`; changing it (`update_pantry`, `put_away_shopping_items`) needs the `pantry:write` permission. A connection made before that permission existed does not have it: remove the connector in claude.ai and add it again, then approve the new permission. If you see an `invalid_scope` error while reconnecting, that is why; removing and re-adding the connector clears it.

## Pantry and freshness

Each household has a pantry (the **Pantry** item in the side rail, just under **Shop**; on mobile, **+** then **Add to pantry**): what you have, where it is (fridge, freezer, cupboard, other), when it was bought and opened, and an optional "use by" date. On the shopping list, **Put away** moves the bought items into the pantry with today's date. A food that is in the pantry counts as "on hand", so shopping lists built from the meal plan skip it.

Mealie only stores the dates. Claude estimates whether something is still good from those dates and general food knowledge, and gives that as guidance, never as food safety advice. The `pantry:write` permission Claude needs to change the pantry is shown as "Manage the pantry" on the consent page.

## Recipe feedback

After cooking, say how it went: **Loved it**, **It was fine** or **Not again**, optionally with how much work it was. Use the buttons at the end of cook mode, or just tell Claude ("the kids loved the lasagne"). Each household keeps its own history: the verdict, the effort, who recorded it, for whom, the date and an optional note. The recipe page shows it under **How it went**. Recording a verdict also moves the recipe's last made date forward, sets the cook's own star rating (5, 3 or 1) and adds a comment to the recipe timeline. Claude sees the last verdict in search results and recent meals, avoids proposing "Not again" recipes unless you ask for one, and prefers "Loved it" ones when you want something reliable. Home's **Make again** shelf leaves out "Not again" recipes. No new permission is needed: reading feedback uses `recipes:read` and recording it uses `recipes:write`, so existing claude.ai connections keep working.

## Household profiles

The **Household** page (user menu, **Household**; also linked from Settings) records who eats here and how you cook. Each person gets a card: a name (linked to a Mealie user or just a name, for example a child), a diet, allergies, foods never to serve, dislikes, likes and a note. **How we cook** holds the default servings, the quick weekdays, the longest cooking time on weeknights and at the weekend, favourite cuisines and a note. Any member of the household can edit it. Claude reads all of it in `get_household_context`: allergies and "never serve" foods are hard constraints, dislikes are avoided unless you ask, and likes and cuisines are hints. When you tell Claude something new ("Sam doesn't eat mushrooms"), it records it with `update_household_profile`, asking first unless your own instructions say otherwise (see [Claude writes recipes](#claude-writes-recipes)). That tool can add, edit and remove people and change the cooking habits; its `add_to` mode, the one Claude uses for a single new fact, appends to a list without replacing it. Claude never guesses allergies. No reconnect is needed: reading uses `recipes:read` and writing uses `household:write` ("Edit household settings"), which existing connections already have.

## Claude writes recipes

Claude can put recipes into Mealie itself, owned by you and in your household, as if you had made them in Mealie:

- `create_recipe` saves a recipe Claude wrote: name, servings, times, ingredients, steps (with section titles and timers), tags, categories, tools and notes. Ingredients are stored as quantity, unit and food, so the shopping list, the pantry and scaling work on them. Claude can send them already structured or as plain lines like "200 g spaghetti", which Mealie's own ingredient parser splits; a line it can't split, like "salt to taste", is kept as a note. Unknown foods, units, tags, categories and tools are created; a food also matches its simple singular or plural ("egg" and "eggs" are one food). If recipes with the same name exist, the answer lists them so Claude can mention them.
- `import_recipe_from_url` imports a web page with Mealie's own importer (the same one as importing a URL in Mealie), downloads its image and parses its ingredients straight away. A page already imported into your group is not imported twice: Claude gets the existing recipe back. A recipe Claude adapted from that page counts as imported from it.
- `update_recipe` changes an existing recipe: only the fields sent change, and a list that is sent (ingredients, steps, tags...) replaces the old one. It keeps the step timers, sections and step-to-ingredient links that the new lists still match. `scale_to_servings` scales every quantity ("make the carbonara for 4"); lines without a quantity are left as they are and listed. Claude can edit what you could edit in Mealie: a locked recipe only if it is yours (or you are an admin), and another household's recipe only when that household allows it.
- `set_recipe_image` gives a recipe a photo found online, replacing the current one. Claude passes a direct link to the picture (from an image search or the page's image); Mealie downloads it, checks it is a real picture and makes its sizes, the same way as setting an image from a URL in Mealie. Only public links are fetched (never an address on your home network), up to 15 MB. If the download fails, the recipe keeps its current photo and Claude can try another picture.

A typical evening: you say what you feel like, Claude writes the recipe, saves it with `create_recipe`, gives it a photo with `set_recipe_image` and adds it to tonight with `add_mealplan_entries`. No reconnect is needed: these tools use `recipes:write`, which existing connections already have.

**Confirming.** Claude follows your own instructions about confirming changes, for every write tool. If you haven't said anything, it shows what it will write and asks first. That way your own claude.ai skills and instructions decide: one that says "save recipes without asking" makes recipe writing a single step, and one that says "always show me first" keeps the check. Mealie doesn't force an extra yes on top.

## Verify

```bash
curl https://<domain>/.well-known/oauth-authorization-server
curl https://<domain>/.well-known/oauth-protected-resource/mcp
# unauthenticated MCP calls must be rejected with 401 and a WWW-Authenticate header
curl -i -X POST https://<domain>/mcp
```

The protected-resource document should report `"resource": "https://<domain>/mcp"`.
