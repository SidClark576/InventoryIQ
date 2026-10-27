#!/usr/bin/env bash
# `npm run dev:local`: fake AWS (Floci in Docker) + seeded test store + local API runner + Vite. Ctrl-C stops all.
# Ports: LOCAL_FLOCI_PORT (4566), LOCAL_API_PORT (3001), LOCAL_DEV_PORT (8000). See AGENTS.md "Local backend".
set -euo pipefail
cd "$(dirname "$0")/.."
FLOCI_IMAGE=floci/floci:2.3.0
export LOCAL_API_PORT="${LOCAL_API_PORT:-3001}" LOCAL_DEV_PORT="${LOCAL_DEV_PORT:-8000}"
export LOCAL_AWS_URL="http://localhost:${LOCAL_FLOCI_PORT:-4566}"
docker info >/dev/null 2>&1 || { echo "Docker is not running: start Docker Desktop, then retry." >&2; exit 1; }
docker image inspect "$FLOCI_IMAGE" >/dev/null 2>&1 \
  || { echo "Floci image missing: run 'docker pull $FLOCI_IMAGE' once, then retry." >&2; exit 1; }
trap 'kill $(jobs -p) 2>/dev/null; docker rm -f panindo-floci >/dev/null 2>&1' EXIT

# In-memory (no volumes), no Docker socket: data resets on every start and the seed below recreates it.
docker run -d --rm --name panindo-floci -p "127.0.0.1:${LOCAL_FLOCI_PORT:-4566}:4566" "$FLOCI_IMAGE" >/dev/null
for _ in $(seq 50); do curl -sf "$LOCAL_AWS_URL/_floci/health" >/dev/null && break; sleep 0.2; done
curl -sf "$LOCAL_AWS_URL/_floci/health" >/dev/null || { echo "Floci did not start (docker logs panindo-floci)" >&2; exit 1; }

.venv/bin/python scripts/local_api.py &
.venv/bin/python scripts/local_seed.py
VITE_API_BASE="http://localhost:$LOCAL_API_PORT" npx vite --port "$LOCAL_DEV_PORT" --strictPort
