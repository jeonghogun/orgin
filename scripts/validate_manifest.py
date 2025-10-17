#!/usr/bin/env python3
"""Validate artifacts/manifest.json and optional .sha256 files."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "artifacts" / "manifest.json"


def load_manifest() -> Dict:
    if not MANIFEST.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST}")
    with MANIFEST.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: Path, chunk_size: int = 65536) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_sha256_sidecar(path: Path) -> str | None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists():
        with sidecar.open("r", encoding="utf-8") as fh:
            token = fh.read().strip().split()[0]
        return token
    return None


def validate_entry(base: Path, entry: Dict) -> Dict:
    rel_path = entry.get("path")
    status = entry.get("status", "active")
    result = {
        "path": rel_path,
        "phase": entry.get("phase"),
        "status": status,
        "exists": False,
        "hash_match": False,
        "expected": entry.get("sha256"),
        "computed": None,
    }
    if status == "planned":
        result["hash_match"] = True
        result["exists"] = False
        result["note"] = "Planned artifact; skipping validation"
        return result
    if not rel_path:
        result["error"] = "Missing path"
        return result
    file_path = base / rel_path
    if not file_path.exists():
        result["error"] = "Missing file"
        return result
    result["exists"] = True
    expected = entry.get("sha256")
    sidecar_hash = read_sha256_sidecar(file_path)
    if expected is None and sidecar_hash:
        expected = sidecar_hash
    if expected is None:
        result["error"] = "Missing sha256"
        return result
    computed = sha256_file(file_path)
    result["computed"] = computed
    result["hash_match"] = computed == expected
    if not result["hash_match"]:
        result["error"] = "Hash mismatch"
    return result


def summarize(results: Iterable[Dict]) -> List[Dict]:
    return [r for r in results]


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-existing-artifacts", action="store_true", help="No-op flag for interface parity")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    entries = manifest.get("artifacts", [])
    if not entries:
        print("Manifest contains no artifacts. Add entries when artifacts become available.")
        return 0

    base = MANIFEST.parent
    results = [validate_entry(base, entry) for entry in entries]
    failures = [r for r in results if r.get("status") != "planned" and not r.get("hash_match")]

    print("Phase | Path | Status | Exists | HashMatch")
    print("----- | ---- | ------ | ------ | ---------")
    for result in results:
        print(
            f"{result.get('phase')} | {result.get('path')} | {result.get('status')} | "
            f"{result.get('exists')} | {result.get('hash_match')}"
        )
        if note := result.get("note"):
            print(f"  -> {note}")
        if error := result.get("error"):
            print(f"  -> {error}")
    if failures:
        print(f"Validation failed for {len(failures)} artifacts.", file=sys.stderr)
        return 2
    print("All artifact hashes verified or pending as planned entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
