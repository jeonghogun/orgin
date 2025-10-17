.PHONY: docs manifest lint paper sync tests

docs:
./scripts/build_docs.sh --use-existing-artifacts

manifest:
python scripts/validate_manifest.py --use-existing-artifacts

lint:
python -m compileall src

paper:
./scripts/arxiv_pack.sh --dry-run

sync:
python scripts/sync_figs_and_tables.py --dry-run

tests:
pytest tests/test_soft_ops.py tests/test_dataloader.py tests/test_heads.py
