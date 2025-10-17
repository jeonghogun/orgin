# Contributing to SEMM

Thank you for considering a contribution to SEMM: Structure-Embedded Meaning Modeling.

## Development environment
- Python 3.11
- Poetry or `pip` with `requirements-dev.txt`
- No external network calls during builds; rely on pinned artifacts in `artifacts/`

## Workflow
1. Fork the repository and create a feature branch.
2. Run `pre-commit run --all-files` (see `.pre-commit-config.yaml` when available).
3. Execute `scripts/validate_manifest.py` and the smoke tests in `scripts/`.
4. Open a pull request referencing relevant phases (P0–P39).

## Coding guidelines
- Keep modules deterministic; thread seeds via `cfg/` where applicable.
- Add module-level README updates for any new package.
- Ensure new artifacts are registered in `artifacts/manifest.json` with `sha256` hashes.
- Provide unit tests for new functionality (see `tests/` for structure).

## Documentation
- Update MkDocs pages under `docs/` and ensure `scripts/build_docs.sh` succeeds.
- For paper-related changes, run `scripts/sync_figs_and_tables.py` followed by `scripts/arxiv_pack.sh --dry-run`.

## Reporting issues
Please file an issue with:
- Phase identifier(s)
- Expected vs. actual behavior
- Steps to reproduce
- Relevant artifact or log references

By contributing you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
