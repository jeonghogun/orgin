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
FAIL_RATIO=${LOCUST_FAIL_RATIO:-0.01}
EXIT_CODE=${LOCUST_EXIT_CODE:-1}

echo "Running Locust smoke test against $HOST with $USERS users for $RUN_TIME..."

locust -f locustfile.py \
  --headless \
  --users "$USERS" \
  --spawn-rate "$SPAWN_RATE" \
  --run-time "$RUN_TIME" \
  --stop-timeout 30 \
  --fail-ratio "$FAIL_RATIO" \
  --exit-code-on-error "$EXIT_CODE" \
  --exit-code-on-fail "$EXIT_CODE" \
  --host "$HOST"
