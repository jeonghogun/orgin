# Artifact Catalog

`artifacts/manifest.json` enumerates every frozen output supporting SEMM phases. Each entry contains:

- `phase`: Identifier (e.g., `P11`)
- `name`: Canonical file label
- `path`: Relative path within `artifacts/`
- `sha256`: Content hash
- `size`: Bytes on disk
- `purpose`: Narrative description
- `status`: `active`, `superseded`, or `planned`

## Validation workflow
1. `python scripts/validate_manifest.py`
2. Inspect the emitted table highlighting missing files or hash mismatches
3. Regenerate only if needed; otherwise mark entries as `planned`

## Tables and figures
Run `python scripts/gen_tables_index.py` to generate `docs/tables.md`, which links each CSV to its phase context. Figures are synced via `scripts/sync_figs_and_tables.py` into `paper_src/` with canonical names (e.g., `fig9_error_cases.png`).

## Bundles
Bundle archives collect metrics, dashboards, and guardrail reports for quick sharing. They should include an embedded `manifest.json` documenting all contained assets.
