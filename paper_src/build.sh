#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--dry-run]

Build the arXiv-ready bundle from Markdown sources. Requires pandoc if not run in dry-run mode.
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

OUTPUT_DIR="build"
mkdir -p "$OUTPUT_DIR"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[DRY-RUN] Would invoke pandoc to compile paper_src/paper.md"
  exit 0
fi

if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc is required to build the paper. Install pandoc or run with --dry-run." >&2
  exit 1
fi

pandoc paper.md --from markdown --to pdf --output "$OUTPUT_DIR/semm_paper.pdf" \
  --metadata-file=../CITATION.cff \
  --include-in-header=tables.tex \
  --include-in-header=figures.tex

echo "Paper bundle written to $OUTPUT_DIR/semm_paper.pdf"
