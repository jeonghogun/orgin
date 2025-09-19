#!/bin/bash

set -euo pipefail

echo "Setting up test environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# Ensure Python can resolve project modules while still respecting any existing configuration.
export PYTHONPATH="${PYTHONPATH:-$REPO_ROOT}"

# Provide a sensible default for DATABASE_URL when one isn't supplied by the environment.
export DATABASE_URL="${DATABASE_URL:-postgresql://user:password@localhost:5433/test_origin_db}"

if [ -n "${PYTHON:-}" ] && command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON_EXEC="$(command -v "$PYTHON")"
elif [ -n "${VIRTUAL_ENV:-}" ]; then
    PYTHON_EXEC="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXEC="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_EXEC="$(command -v python)"
else
    echo "Unable to locate a Python interpreter." >&2
    exit 1
fi

echo "Running tests..."
if [ $# -eq 0 ]; then
    echo "Running all tests..."
    "$PYTHON_EXEC" -m pytest tests
else
    echo "Running specific tests: $*"
    "$PYTHON_EXEC" -m pytest "$@"
fi

echo "Test run complete!"
