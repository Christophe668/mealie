#!/usr/bin/env bash
# Runs the fork locally: FastAPI backend on :9000 and the Nuxt frontend on :3000, in one terminal.
# Ctrl-C (or stopping the T3 script) stops both. Earlier Mealie dev servers still holding those ports are
# stopped first; anything else on the ports is left alone and reported.
set -euo pipefail
cd "$(dirname "$0")/.."

repo_root=$(pwd -P)

free_port() {
  local port=$1 pids pid cmd cwd
  pids=$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)
  for pid in $pids; do
    cmd=$(ps -o command= -p "$pid" 2>/dev/null || true)
    # the backend's auto-reload worker shows no "mealie" in its command line, so also match on its working folder
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' || true)
    if [[ "$cmd" == *mealie* || "$cmd" == *nuxt* || "$cwd" == "$repo_root"* ]]; then
      echo "Stopping the earlier Mealie server on :${port} (pid ${pid})"
      kill "$pid" 2>/dev/null || true
    else
      echo "Port ${port} is used by another program (pid ${pid}: ${cmd}). Stop it and run again." >&2
      exit 1
    fi
  done
}

free_port 9000
free_port 3000
sleep 1

cleanup() {
  trap - INT TERM EXIT
  echo "Stopping Mealie"
  kill 0 2>/dev/null || true
}
trap cleanup INT TERM EXIT

task py &
task ui &

for _ in $(seq 1 120); do
  if curl -fs -o /dev/null http://localhost:9000/api/app/about && curl -fs -o /dev/null http://localhost:3000/login; then
    echo "Mealie is ready: http://localhost:3000"
    break
  fi
  sleep 1
done

wait
