# SEMM: Structure-Embedded Meaning Modeling

SEMM delivers an end-to-end delta → line → surface modeling pipeline that couples policy, planning, uncertainty estimation, and online A/B simulation. The repository contains production-ready assets for P0–P28 along with a forward-looking scaffold for P30–P39 LLM expansion.

## Project status
- **Implemented**: P0–P10, P11, P12–P16, P18–P23, P24–P28 (validated by the shipped artifacts, dashboards, and guardrail reports).
- **Planned**: P30–P39 LLM expansion roadmap including streaming data, surrogate modeling, encoder/decoder heads, objectives, training loop, inference, retrieval, evaluation, and batch simulation.

## Repository layout
- `src/` — Python sources (`semm` core packages, P0–P28 implementation, P30–P39 scaffold).
- `artifacts/` — Frozen outputs (figures, tables, bundles) with manifest and hashes.
- `docs/` — MkDocs documentation site with per-phase pages and artifact index.
- `paper_src/` — arXiv-ready manuscript skeleton with linked tables and figures.
- `scripts/` — Build, validation, and packaging helpers (deterministic, dry-run friendly).
- `ci/` — Auxiliary configuration referenced by CI workflows.
- `.github/workflows/` — CI entrypoints (lint, manifest validation, smoke tests).
- `examples/` — Lightweight notebooks and CLI cheat sheets using existing artifacts.

Legacy directories (e.g., `app/`, `alembic/`) remain untouched for historical reference and will be migrated into `src/semm` in subsequent clean-up passes.

## Quickstart
1. **Validate artifacts**
   ```bash
   python scripts/validate_manifest.py --use-existing-artifacts
   ```
2. **Build documentation**
   ```bash
   ./scripts/build_docs.sh --use-existing-artifacts
   ```
3. **Assemble paper bundle**
   ```bash
   ./scripts/arxiv_pack.sh --dry-run
   ```
4. **Explore manifest**
   ```bash
   python examples/quickstart.ipynb
   ```

All commands operate in dry-run or “use existing artifacts” mode to avoid regenerating expensive assets.

## Links
- [Documentation](docs/index.md)
- [Paper source](paper_src/paper.md)
- [Artifacts](artifacts/README.md)
- [Figures](paper_src/figures.tex)
- [Tables](paper_src/tables.tex)
- [Related project (lineweave)](https://github.com/jeonghogun/lineweave)

## License
Released under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0). Attribution to **Jeong Ho Gun et al.** is required for all derivative works.

## Citation
See [`CITATION.cff`](CITATION.cff) for citation metadata. A BibTeX entry is provided there for convenience.
