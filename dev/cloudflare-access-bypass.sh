#!/usr/bin/env bash
# Creates a Cloudflare Access application that lets claude.ai's servers reach Mealie's MCP and OAuth endpoints
# without the Access login, while the rest of the hostname stays behind Access. These paths remain protected
# by Mealie itself: /mcp needs an OAuth token the user approved on Mealie's consent page.
#
# One-time, store a Cloudflare API token (My Profile > API Tokens > Create Token > Custom token,
# permission: Account > Access: Apps and Policies > Edit, for your account):
#   security add-generic-password -a "$USER" -s cloudflare-api-token -w
#
# Usage:
#   CF_ACCOUNT_ID=<id> MEALIE_HOST=mealie.example.com ./dev/cloudflare-access-bypass.sh
set -euo pipefail

: "${CF_ACCOUNT_ID:?set CF_ACCOUNT_ID (the id in your dash.cloudflare.com URL)}"
: "${MEALIE_HOST:?set MEALIE_HOST, e.g. mealie.example.com}"
APP_NAME="Mealie: Claude connector (bypass)"
API="https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps"

token=$(security find-generic-password -a "$USER" -s cloudflare-api-token -w 2>/dev/null) || {
  echo "No Cloudflare API token in the keychain. Store it first:" >&2
  echo "  security add-generic-password -a \"\$USER\" -s cloudflare-api-token -w" >&2
  exit 1
}
cf() { curl -s -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" "$@"; }

existing=$(cf "$API?per_page=100" | APP_NAME="$APP_NAME" python3 -c '
import sys, json, os
d = json.load(sys.stdin)
if not d.get("success"):
    print("ERR " + json.dumps(d.get("errors"))); sys.exit()
print(next((a["id"] for a in d["result"] if a.get("name") == os.environ["APP_NAME"]), ""))')
if [[ "$existing" == ERR* ]]; then echo "Cloudflare refused the request: ${existing#ERR }" >&2; exit 1; fi

payload=$(MEALIE_HOST="$MEALIE_HOST" APP_NAME="$APP_NAME" python3 - <<'PY'
import json, os
host = os.environ["MEALIE_HOST"]
paths = ["mcp", ".well-known/*", "register", "token"]
print(json.dumps({
    "name": os.environ["APP_NAME"],
    "type": "self_hosted",
    "domain": f"{host}/{paths[0]}",
    "destinations": [{"type": "public", "uri": f"{host}/{p}"} for p in paths],
    "session_duration": "24h",
    "app_launcher_visible": False,
    "policies": [{"name": "Bypass for the Claude connector", "decision": "bypass", "include": [{"everyone": {}}]}],
}))
PY
)

if [[ -n "$existing" ]]; then
  echo "Updating the existing Access application (${existing})"
  response=$(cf -X PUT "$API/$existing" -d "$payload")
else
  echo "Creating the Access application"
  response=$(cf -X POST "$API" -d "$payload")
fi
python3 -c '
import sys, json
d = json.load(sys.stdin)
if d.get("success"):
    a = d["result"]; print("OK:", a["name"], "->", ", ".join(x["uri"] for x in a.get("destinations", [])))
else:
    print("Cloudflare answered:", json.dumps(d.get("errors"))); sys.exit(1)' <<<"$response"
