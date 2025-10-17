"""Training loop stub for P33 objectives and P34 gains."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from semm.p2.llm.models.dec_linehead import LineDecoderHead, mean_absolute_percentage_error
from semm.p2.llm.models.enc_delta import DeltaEncoder, evaluate_macro_f1
from semm.p2.llm.objectives import contrast, losses, regularizers

DELTA_F1_TARGET = 0.60
COST_MAPE_TARGET = 0.20
SEMANTIC_GAIN_TARGET = 0.05
JACCARD_GAIN_TARGET = 0.05


@dataclass
class TrainConfig:
    learning_rate: float = 1e-3
    epochs: int = 1
    dry_run: bool = True


def train_step(batch: Dict[str, np.ndarray], encoder: DeltaEncoder, head: LineDecoderHead) -> Dict[str, float]:
    features = encoder(batch["tokens"], batch["deltas"], batch["lines"])
    head_out = head(features.delta_features)

    ml_loss = losses.multilabel_bce(head_out.delta_logits, batch["labels"])
    cost_loss = losses.cost_regression_loss(head_out.cost_pred, batch["costs"])
    reg_loss = regularizers.curvature_penalty(batch["lines"]) + regularizers.length_penalty(batch["lines"])
    total_loss = ml_loss + cost_loss + 0.01 * reg_loss

    return {
        "multilabel_loss": ml_loss,
        "cost_loss": cost_loss,
        "reg_loss": reg_loss,
        "total_loss": total_loss,
    }


def evaluate(batch: Dict[str, np.ndarray], encoder: DeltaEncoder, head: LineDecoderHead) -> Dict[str, float]:
    features = encoder(batch["tokens"], batch["deltas"], batch["lines"])
    head_out = head(features.delta_features)

    macro_f1 = evaluate_macro_f1(head_out.delta_logits, batch["labels"])
    cost_mape = mean_absolute_percentage_error(head_out.cost_pred, batch["costs"])
    semantic_delta = contrast.semantic_gain(0.05)
    jaccard_delta = contrast.jaccard_gain(0.05)

    return {
        "macro_f1": macro_f1,
        "cost_mape": cost_mape,
        "semantic_gain": semantic_delta,
        "jaccard_gain": jaccard_delta,
    }


def train_loop(config: TrainConfig, batch: Dict[str, np.ndarray]) -> Dict[str, float]:
    encoder = DeltaEncoder()
    head = LineDecoderHead()
    metrics = train_step(batch, encoder, head)
    eval_metrics = evaluate(batch, encoder, head)
    metrics.update(eval_metrics)

    if metrics["macro_f1"] < DELTA_F1_TARGET:
        print(f"[WARN] Macro-F1 {metrics['macro_f1']:.3f} below target {DELTA_F1_TARGET:.2f}")
    if metrics["cost_mape"] > COST_MAPE_TARGET:
        print(f"[WARN] Cost MAPE {metrics['cost_mape']:.3f} above target {COST_MAPE_TARGET:.2f}")
    if metrics["semantic_gain"] < SEMANTIC_GAIN_TARGET:
        print(f"[WARN] Semantic gain {metrics['semantic_gain']:.3f} below target {SEMANTIC_GAIN_TARGET:.2f}")
    if metrics["jaccard_gain"] < JACCARD_GAIN_TARGET:
        print(f"[WARN] Jaccard gain {metrics['jaccard_gain']:.3f} below target {JACCARD_GAIN_TARGET:.2f}")
    return metrics
