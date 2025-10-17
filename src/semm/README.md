# SEMM Python Package

The `semm` package hosts the production implementation of the Structure-Embedded Meaning Modeling pipeline.

## Structure
- `p1/`: Legacy P0–P10 implementation (to be migrated from historical modules).
- `p2/`: Advanced phases P11–P28 and the LLM expansion scaffold (P30–P39).

## Purpose
Provide reusable modules for delta extraction, line synthesis, surface modeling, policy optimization, planning, uncertainty estimation, A/B simulation, and future LLM enhancements.

## Inputs
Artifacts stored under `artifacts/` (see `artifacts/manifest.json`).

## Outputs
Derived figures, tables, and evaluation bundles defined per phase.

## CLI
Each module exposes a `python -m` entrypoint with `--dry-run` and `--use-existing-artifacts` options.

## Acceptance metrics
- P0–P28 metrics are locked to historical thresholds documented in `docs/phases/` pages.
- P30–P39 targets are embedded as docstrings within the scaffold modules.

## Example
```bash
python -m semm.p2.planner --dry-run --use-existing-artifacts
```
