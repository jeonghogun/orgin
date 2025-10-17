# `semm.p2` Package

`semm.p2` houses advanced modules covering P11–P28 (policy, planner, uncertainty, deployment) and the forthcoming P30–P39 LLM roadmap.

## Purpose
- Execute policy improvements (P11)
- Model residual scalar fields (P12–P16)
- Manage planner loops, uncertainty quantification, A/B experimentation (P18–P23)
- Operate dashboards, bundles, and guardrails (P24–P28)
- Provide scaffolding for LLM integration (P30–P39)

## Inputs
- Policy checkpoints, planner configs, and manifest-indexed artifacts
- LLM roadmap data described in `llm/data/schema.md`

## Outputs
- Updated deployment candidate bundles
- Evaluation reports in `artifacts/llm_eval/`
- Dashboard assets in `artifacts/dashboard/`

## CLI
```bash
python -m semm.p2.policy --use-existing-artifacts
python -m semm.p2.uncertainty --dry-run
python -m semm.p2.llm.train_loop --config cfg/train_llm.yaml --dry-run
```

## Key files
- `llm/data/`: loaders for streaming ingest (P30)
- `llm/surrogate/`: differentiable edit cost surrogate (P31)
- `llm/models/`: encoder, decoder heads, adapters (P32–P33)
- `llm/objectives/`: loss components (P33–P34)
- `llm/infer/`: inference pipeline and guardrails (P37)
- `llm/eval/`: evaluation harness (P36, P38)
- `llm/batch_sim/`: serving simulations (P39)

## Acceptance metrics
- Policy macro-F1 ≥ 0.49 (current)
- Guardrail violations ≤ 0.5% (target)
- LLM metrics embedded as docstrings in scaffold modules

## Example workflow
```bash
python -m semm.p2.llm.batch_sim.run --config cfg/infer.yaml --dry-run
```
