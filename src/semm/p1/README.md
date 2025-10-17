# `semm.p1` Package

`semm.p1` maintains the foundational P0–P10 modules responsible for ingesting templates, parsing deltas, generating line representations, fitting surfaces, and conducting ablation studies.

## Purpose
Provide stable, hash-checked implementations backing historical artifacts.

## Inputs
- `artifacts/p10_real/p1_parsed.jsonl`
- `artifacts/p10_real/p4_deltas.jsonl`
- `artifacts/p10_real/generated_paths.jsonl`
- `artifacts/p10_real/p8/surface_coords.jsonl`

## Outputs
- Intermediate JSONL files per phase
- Metrics tables in `artifacts/tables/`
- Figures summarizing delta/line/surface performance

## CLI
```bash
python -m semm.p1.delta --use-existing-artifacts
python -m semm.p1.line --dry-run
```

## Key algorithms
- Template normalization and schema enforcement
- Delta extraction with loop-invariant checks
- Line generation with curvature constraints
- Surface fitting via radial basis surfaces

## Acceptance metrics
- Macro-F1 ≥ 0.45 on delta extraction
- Surface RMSE ≤ 0.08 (normalized units)

## Example workflow
```bash
python -m semm.p1.pipeline --use-existing-artifacts --summary artifacts/tables/p0_p10_summary.csv
```
