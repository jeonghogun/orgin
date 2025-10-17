#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--use-existing-artifacts] [--dry-run]

Build the MkDocs site into the local `site/` directory.
USAGE
}

USE_EXISTING=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --use-existing-artifacts)
      USE_EXISTING=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[DRY-RUN] Would build MkDocs site"
  exit 0
fi

if [[ "$USE_EXISTING" -eq 1 ]]; then
  echo "Using existing artifacts. No downloads or regeneration will occur."
fi

if ! command -v mkdocs >/dev/null 2>&1; then
  echo "mkdocs is required. Install it via 'pip install mkdocs-material' or run with --dry-run." >&2
  exit 1
fi

mkdocs build --strict
