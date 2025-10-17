# Reproducibility Protocol

SEMM artifacts are frozen outputs generated on a MacBook Air M4 15" running macOS 15 with Python 3.11. All experiments are deterministic and re-runnable using the manifest and scripts contained in this repository.

## Environment
- Python 3.11
- `pip install -r requirements.txt`
- Local CPU execution only; GPU jobs are skipped via `--use-existing-artifacts`
- Environment variables: `PYTHONHASHSEED=0`, `SEMM_DETERMINISTIC=1`

## Determinism
- Seeds are threaded through `cfg/*.yaml`
- Artifacts are content-addressed via SHA-256 hashes
- No external downloads; all data lives under `artifacts/`

## Steps to verify
1. `python scripts/validate_manifest.py`
2. `./scripts/build_docs.sh --use-existing-artifacts`
3. `./scripts/sync_figs_and_tables.py --dry-run`
4. `./scripts/arxiv_pack.sh --dry-run`

## Manifest
`artifacts/manifest.json` enumerates every required output. The validation script checks for the presence of each file and verifies hashes using precomputed `.sha256` companions.

## Reporting
If reproducibility issues arise, file an issue that includes:
- Phase identifiers affected
- Manifest entries involved
- Logs or hash mismatches

