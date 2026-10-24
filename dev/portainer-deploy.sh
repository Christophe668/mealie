#!/usr/bin/env bash
# Creates (or updates) the "mealie" stack in Portainer from this repository's docker-compose.nas.yml,
# through Portainer's API. Secrets never appear on the command line or in the output:
#   - the Portainer API key is read from the macOS keychain item "portainer-api-key";
#   - the Postgres password is generated once and kept in the keychain item "mealie-postgres-password".
#
# One-time, store your Portainer API key (Portainer > My account > Access tokens > Add access token):
#   security add-generic-password -a "$USER" -s portainer-api-key -w
#   (it prompts for the key; nothing is echoed)
#
# Usage:
#   PORTAINER_URL=https://192.168.1.20:9443 BASE_URL=https://mealie.example.com ./dev/portainer-deploy.sh
# Optional: DATA_ROOT=/volume1/docker/mealie (default), ENDPOINT_ID (auto-detected when there is one environment),
#           DRY_RUN=1 to print the request without the password and without sending it.
set -euo pipefail

: "${PORTAINER_URL:?set PORTAINER_URL, e.g. https://192.168.1.20:9443}"
: "${BASE_URL:?set BASE_URL, e.g. https://mealie.example.com}"
DATA_ROOT="${DATA_ROOT:-/volume1/docker/mealie}"
STACK_NAME="mealie"
REPO_URL="https://github.com/Christophe668/mealie"
PORTAINER_URL="${PORTAINER_URL%/}"

[[ "$BASE_URL" == https://* ]] || { echo "BASE_URL must start with https://" >&2; exit 1; }

api_key=$(security find-generic-password -a "$USER" -s portainer-api-key -w 2>/dev/null) || {
  echo "No Portainer API key in the keychain. Store it first:" >&2
  echo "  security add-generic-password -a \"\$USER\" -s portainer-api-key -w" >&2
  exit 1
}

pg_password=$(security find-generic-password -a "$USER" -s mealie-postgres-password -w 2>/dev/null || true)
if [[ -z "$pg_password" ]]; then
  pg_password=$(openssl rand -base64 30 | tr -d '/+=' | cut -c1-32)
  if [[ -z "${DRY_RUN:-}" ]]; then
    security add-generic-password -a "$USER" -s mealie-postgres-password -w "$pg_password"
    echo "Generated a Postgres password and saved it in the keychain (item: mealie-postgres-password)."
  fi
fi

# -k: Portainer on a NAS usually serves a self-signed certificate.
api() { curl -sk -H "X-API-Key: ${api_key}" -H "Content-Type: application/json" "$@"; }

if [[ -z "${ENDPOINT_ID:-}" ]]; then
  endpoints=$(api "${PORTAINER_URL}/api/endpoints") || { echo "Cannot reach Portainer at ${PORTAINER_URL}" >&2; exit 1; }
  count=$(python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else -1)' <<<"$endpoints")
  if [[ "$count" == "-1" ]]; then echo "Portainer refused the API key: ${endpoints}" >&2; exit 1; fi
  if [[ "$count" != "1" ]]; then
    echo "Portainer has ${count} environments; set ENDPOINT_ID to one of:" >&2
    python3 -c 'import sys,json; [print(f"  {e[\"Id\"]}: {e[\"Name\"]}") for e in json.load(sys.stdin)]' <<<"$endpoints" >&2
    exit 1
  fi
  ENDPOINT_ID=$(python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["Id"])' <<<"$endpoints")
fi

payload=$(STACK_NAME="$STACK_NAME" REPO_URL="$REPO_URL" BASE_URL="$BASE_URL" DATA_ROOT="$DATA_ROOT" PG="$pg_password" python3 - <<'PY'
import json, os
print(json.dumps({
    "name": os.environ["STACK_NAME"],
    "repositoryURL": os.environ["REPO_URL"],
    "repositoryReferenceName": "refs/heads/main",
    "composeFile": "docker-compose.nas.yml",
    "repositoryAuthentication": False,
    "env": [
        {"name": "BASE_URL", "value": os.environ["BASE_URL"]},
        {"name": "POSTGRES_PASSWORD", "value": os.environ["PG"]},
        {"name": "DATA_DIR", "value": os.environ["DATA_ROOT"] + "/data"},
        {"name": "PG_DATA_DIR", "value": os.environ["DATA_ROOT"] + "/pgdata"},
    ],
}))
PY
)

if [[ -n "${DRY_RUN:-}" ]]; then
  echo "Would POST to ${PORTAINER_URL}/api/stacks/create/standalone/repository?endpointId=${ENDPOINT_ID}:"
  python3 -c 'import sys,json; d=json.load(sys.stdin); [e.update(value="***") for e in d["env"] if e["name"]=="POSTGRES_PASSWORD"]; print(json.dumps(d, indent=2))' <<<"$payload"
  exit 0
fi

existing=$(api "${PORTAINER_URL}/api/stacks" | python3 -c "import sys,json; print(next((s['Id'] for s in json.load(sys.stdin) if s['Name']=='${STACK_NAME}' and s['EndpointId']==${ENDPOINT_ID}), ''))")
if [[ -n "$existing" ]]; then
  echo "A stack named ${STACK_NAME} already exists (id ${existing}). Update it in Portainer with Pull and redeploy." >&2
  exit 1
fi

echo "Creating the ${STACK_NAME} stack in Portainer (environment ${ENDPOINT_ID}); pulling images can take a few minutes…"
response=$(api -X POST --max-time 900 "${PORTAINER_URL}/api/stacks/create/standalone/repository?endpointId=${ENDPOINT_ID}" -d "$payload")
if python3 -c 'import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get("Id") else 1)' <<<"$response" 2>/dev/null; then
  echo "Stack created. On your home network open http://<nas-ip>:9925, sign in with changeme@example.com / MyPassword,"
  echo "change the email and password, then add the route to your Cloudflare tunnel."
else
  echo "Portainer answered: ${response}" >&2
  exit 1
fi
