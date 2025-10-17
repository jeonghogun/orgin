#!/usr/bin/env python3
"""Generate docs/tables.md index from artifacts tables."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT / "artifacts" / "tables"
OUTPUT = ROOT / "docs" / "tables.md"
MANIFEST = ROOT / "artifacts" / "manifest.json"

def load_manifest_phases() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for entry in data.get("artifacts", []):
        mapping[entry.get("path", "")] = entry.get("phase", "")
    return mapping

def main() -> None:
    manifest_map = load_manifest_phases()
    lines = ["# Tables Index", ""]
    if not TABLES_DIR.exists():
        lines.append("No tables directory found. Populate artifacts/tables/ to enable indexing.")
    else:
        lines.append("| Table | Phase | Path |")
        lines.append("| ----- | ----- | ---- |")
        for csv in sorted(TABLES_DIR.rglob("*.csv")):
            rel = csv.relative_to(ROOT)
            phase = manifest_map.get(str(rel.relative_to("artifacts")), "")
            lines.append(f"| `{csv.name}` | {phase or '—'} | `{rel}` |")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()
