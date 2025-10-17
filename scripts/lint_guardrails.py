#!/usr/bin/env python3
"""Check guardrail policies (P25)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARDRAIL_FILE = ROOT / "artifacts" / "p25_guardrails" / "log.jsonl"


def load_guardrails(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[WARN] Guardrail log missing: {path}")
        return []
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))
    return records


def main() -> int:
    records = load_guardrails(GUARDRAIL_FILE)
    violations = [r for r in records if r.get("violation", False)]
    rate = (len(violations) / len(records)) if records else 0.0
    print(f"Guardrail violations: {len(violations)} / {len(records)} ({rate:.2%})")
    if rate > 0.005:
        print("[WARN] Violation rate exceeds 0.5% target")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
