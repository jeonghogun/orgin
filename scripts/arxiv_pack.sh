#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--dry-run]

Create an arXiv uploadable zip containing paper sources and referenced figures/tables.
USAGE
}

DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
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

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PACK_DIR="$ROOT/paper_src"
OUTPUT="$ROOT/paper_src/semm_arxiv.zip"

FILES=(
  "paper_src/paper.md"
  "paper_src/tables.tex"
  "paper_src/figures.tex"
)

while IFS= read -r -d '' file; do
  FILES+=("${file#$ROOT/}")
done < <(find "$PACK_DIR" -maxdepth 2 -type f \( -path "*figures/*" -o -path "*tables/*" \) -print0)

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '[DRY-RUN] Would create %s containing:\n' "$OUTPUT"
  printf '  %s\n' "${FILES[@]}"
  exit 0
fi

( cd "$ROOT" && zip -r "$OUTPUT" "${FILES[@]}" )

echo "Created $OUTPUT"
