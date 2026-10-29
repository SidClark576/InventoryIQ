#!/usr/bin/env bash
# Rehearse the org rollout on Floci (scripts/rollout_orgs.py, every step --apply) with main's old-app behaviour
# checked after each step. Own container and ports, so it can run next to `npm run dev:local`. Nothing reaches AWS
# unless you pass --copy-from-live EMAIL (a read-only scan with your AWS_PROFILE). See AGENTS.md "Local backend".
set -euo pipefail
cd "$(dirname "$0")/../.."
FLOCI_IMAGE=floci/floci:2.3.0
NAME=panindo-floci-rollout
export LOCAL_FLOCI_PORT="${LOCAL_FLOCI_PORT:-4567}" LOCAL_API_PORT="${LOCAL_API_PORT:-3101}" LOCAL_API_GATEWAY=1
export LOCAL_AWS_URL="http://localhost:$LOCAL_FLOCI_PORT"
docker info >/dev/null 2>&1 || { echo "Docker is not running: start Docker Desktop, then retry." >&2; exit 1; }
docker image inspect "$FLOCI_IMAGE" >/dev/null 2>&1 \
  || { echo "Floci image missing: run 'docker pull $FLOCI_IMAGE' once, then retry." >&2; exit 1; }
trap 'kill $(jobs -p) 2>/dev/null; docker rm -f $NAME >/dev/null 2>&1' EXIT

# In-memory (no volumes), no Docker socket: functions hold the zips but never run; local_api.py runs the handlers.
# FLOCI_BASE_URL: URLs Floci hands out (SQS queue URLs) use the host port, as local_api.AWS_ENV expects.
docker run -d --rm --name "$NAME" -e FLOCI_BASE_URL="$LOCAL_AWS_URL" -p "127.0.0.1:$LOCAL_FLOCI_PORT:4566" "$FLOCI_IMAGE" >/dev/null
for _ in $(seq 50); do curl -sf "$LOCAL_AWS_URL/_floci/health" >/dev/null && break; sleep 0.2; done
curl -sf "$LOCAL_AWS_URL/_floci/health" >/dev/null || { echo "Floci did not start (docker logs $NAME)" >&2; exit 1; }

.venv/bin/python scripts/local_api.py > "${TMPDIR:-/tmp}/rehearse_rollout_api.log" 2>&1 &
.venv/bin/python scripts/local_seed.py
.venv/bin/python scripts/local/rollout_rehearsal.py "$@"
