# SEMM Documentation

SEMM (Structure-Embedded Meaning Modeling) builds a delta → line → surface representation that powers downstream policy, planning, and evaluation workflows.

## Pipeline overview
1. **P0–P4**: Template normalization, parsing, metric extraction, indexing, delta construction.
2. **P5–P10**: Weight calibration, line generation, benchmarking, surface fitting, correlation analysis, ablation.
3. **P11–P16**: Policy v2, residual scalar field modeling, planner integration.
4. **P18–P23**: Uncertainty quantification, online A/B simulation, CI and drift monitoring.
5. **P24–P28**: Dashboarding, bundle synchronization, guardrail closure.
6. **P30–P39**: Upcoming LLM expansion roadmap.

The documentation site enumerates every phase, artifact, and reproducibility rule. Use the navigation to dive into specific groups.

## Figures
Key publication figures (e.g., `fig9_error_cases.png`) reside under `paper_src/` and are referenced via deterministic file names synced from `artifacts/`.

## Getting started
- Validate artifacts: `python scripts/validate_manifest.py`
- Build docs: `./scripts/build_docs.sh`
- Generate tables index: `python scripts/gen_tables_index.py`

## License
Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0).
