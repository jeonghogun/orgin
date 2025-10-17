# CLI Cheatsheet

## Validation
- `python scripts/validate_manifest.py --use-existing-artifacts`
- `python scripts/lint_guardrails.py`

## Documentation
- `./scripts/build_docs.sh --dry-run`
- `python scripts/gen_tables_index.py`

## Paper
- `./scripts/sync_figs_and_tables.py --dry-run`
- `./scripts/arxiv_pack.sh --dry-run`

## LLM scaffold
- `python -m semm.p2.llm.train_loop --config cfg/train_llm.yaml` (planned)
- `python -m semm.p2.llm.infer.pipeline` (planned)
