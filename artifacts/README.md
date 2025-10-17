# Artifacts Directory

This directory stores immutable outputs from SEMM phases. Files are referenced by `artifacts/manifest.json`, which records phase identifiers, purposes, file sizes, and SHA-256 hashes.

## Layout
- `tables/`: CSV summaries for phases P0–P28
- `figures/`: PNG/SVG renderings for publication
- `bundles/`: Zip archives combining metrics and visualizations
- `llm_eval/`: Reserved for P30–P39 evaluation outputs

## Manifest usage
Run `python scripts/validate_manifest.py` to verify that every manifest entry exists and matches its declared hash. Provide `--use-existing-artifacts` to skip regeneration and rely solely on cached files.

## Adding new artifacts
1. Drop the file in the appropriate subdirectory.
2. Compute SHA-256: `shasum -a 256 <file> > <file>.sha256`
3. Append a manifest entry with phase, purpose, relative path, size in bytes, and hash string.
4. Update the summary table section.

## Non-removal policy
Artifacts are never deleted. If an artifact is superseded, mark it as `"status": "superseded"` in the manifest and link to the replacement.
