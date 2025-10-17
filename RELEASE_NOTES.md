# Release Notes

## v0.9.0 — 2025-10-17
- Completed repository refactor into `src/`, `docs/`, `paper_src/`, `scripts/`, and `artifacts/`.
- Documented P0–P28 outputs with manifest-backed hashes.
- Added MkDocs documentation site, paper source skeleton, and validation scripts.
- Introduced LLM expansion scaffold (P30–P39) with acceptance metrics placeholders.

## Highlights by phase
- **P0–P4**: Template ingestion, parsing, metrics, index construction, delta extraction.
- **P5–P10**: Weight calibration, line generation, benchmarking, surface fits, correlation, ablation studies.
- **P11–P16**: Policy v2 roll-out, residual scalar field, causal interventions, planner integration.
- **P18–P23**: Uncertainty calibration (ECE ≈ 0.08), online A/B simulation, drift monitoring, deployment shortlist.
- **P24–P28**: Dashboard refresh, bundle synchronization, guardrail hardening (P25 violation 0% on top candidates).

## Data refresh
- Integrated the 1k real data refresh with normalized tables and figures.

## Next milestones
- Deliver P30–P39 according to the LLM roadmap: streaming ingest, differentiable surrogate, joint objectives, inference pipeline, retrieval, human evaluation, and serving KPIs.
