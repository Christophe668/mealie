#!/bin/bash

PORT="${API_PORT:-9000}"

if [ -n "$TLS_CERTIFICATE_PATH" ] && [ -n "$TLS_PRIVATE_KEY_PATH" ]; then
  PROTO="https"
else
  PROTO="http"
fi

# -k: TLS certificate is likely not issued for 127.0.0.1, so don't verify
curl -fsk "${PROTO}://127.0.0.1:${PORT}/api/app/about" > /dev/null

# MCP/OAuth routes are only registered when BASE_URL is https or localhost.
case "$BASE_URL" in
  https://* | *localhost* | *127.0.0.1*)
    curl -fsk "${PROTO}://127.0.0.1:${PORT}/.well-known/oauth-protected-resource/mcp" > /dev/null
    ;;
esac
