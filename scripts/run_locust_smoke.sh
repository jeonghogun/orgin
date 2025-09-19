#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v locust >/dev/null 2>&1; then
  echo "Locust is not installed. Please run 'pip install -r requirements-dev.txt' first." >&2
  exit 1
fi

USERS=${LOCUST_USERS:-5}
SPAWN_RATE=${LOCUST_SPAWN_RATE:-2}
RUN_TIME=${LOCUST_RUN_TIME:-1m}
HOST=${LOCUST_HOST:-http://localhost:8080}

echo "Running Locust smoke test against $HOST with $USERS users for $RUN_TIME..."

locust -f locustfile.py \
  --headless \
  --users "$USERS" \
  --spawn-rate "$SPAWN_RATE" \
  --run-time "$RUN_TIME" \
  --stop-timeout 30 \
  --host "$HOST"
