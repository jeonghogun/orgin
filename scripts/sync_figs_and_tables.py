#!/usr/bin/env python3
"""Sync canonical figures and tables from artifacts into paper_src."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
PAPER = ROOT / "paper_src"
FIG_MAP = {
    "semn_1k_normalized_outputs/fig9_error_cases.png": "figures/fig9_error_cases.png",
    "semn_1k_normalized_outputs/fig10_frontier.png": "figures/fig10_frontier.png",
    "semn_1k_normalized_outputs/fig11_param_import.png": "figures/fig11_param_import.png",
    "semn_1k_normalized_outputs/fig12_lang_box.png": "figures/fig12_lang_box.png",
    "paper_pack/fig21_drift_chart.png": "figures/fig21_drift_chart.png",
    "paper_pack/fig22_readiness.png": "figures/fig22_readiness.png",
}
TABLE_MAP = {
    "semn_1k_normalized_outputs/table1_overview.csv": "tables/table1_overview.csv",
    "semn_1k_normalized_outputs/table2_line_metrics.csv": "tables/table2_line_metrics.csv",
    "semn_1k_normalized_outputs/table3_surface_rmse.csv": "tables/table3_surface_rmse.csv",
    "paper_pack/table4_policy.csv": "tables/table4_policy.csv",
    "paper_pack/table5_planner.csv": "tables/table5_planner.csv",
    "paper_pack/table6_uncertainty.csv": "tables/table6_uncertainty.csv",
    "paper_pack/table7_ab.csv": "tables/table7_ab.csv",
    "paper_pack/table8_drift.csv": "tables/table8_drift.csv",
    "paper_pack/table9_guardrails.csv": "tables/table9_guardrails.csv",
    "paper_pack/table10_dashboard.csv": "tables/table10_dashboard.csv",
    "paper_pack/table11_surrogate.csv": "tables/table11_surrogate.csv",
    "paper_pack/table12_joint.csv": "tables/table12_joint.csv",
    "paper_pack/table13_eval.csv": "tables/table13_eval.csv",
    "paper_pack/table14_serving.csv": "tables/table14_serving.csv",
}


def sync(entries: dict[str, str], dry_run: bool) -> None:
    for src_rel, dst_rel in entries.items():
        src = ARTIFACTS / src_rel
        dst = PAPER / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            print(f"[WARN] Missing source {src}")
            continue
        if dry_run:
            print(f"[DRY-RUN] Would copy {src} -> {dst}")
            continue
        shutil.copy2(src, dst)
        print(f"Copied {src} -> {dst}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sync(FIG_MAP, args.dry_run)
    sync(TABLE_MAP, args.dry_run)


if __name__ == "__main__":
    main()
