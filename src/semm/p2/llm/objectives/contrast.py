"""Contrastive objectives for P33–P34."""
from __future__ import annotations

import numpy as np

SEMANTIC_GAIN_TARGET = 0.05
JACCARD_GAIN_TARGET = 0.05


def contrastive_triplet(anchor: np.ndarray, positive: np.ndarray, negative: np.ndarray, margin: float = 0.3) -> float:
    pos_dist = np.linalg.norm(anchor - positive, axis=-1)
    neg_dist = np.linalg.norm(anchor - negative, axis=-1)
    loss = np.maximum(0.0, pos_dist - neg_dist + margin)
    return float(loss.mean())


def semantic_gain(current: float) -> float:
    if current < SEMANTIC_GAIN_TARGET:
        print(f"[WARN] Semantic gain {current:.3f} below target {SEMANTIC_GAIN_TARGET:.2f}")
    return current


def jaccard_gain(current: float) -> float:
    if current < JACCARD_GAIN_TARGET:
        print(f"[WARN] Jaccard gain {current:.3f} below target {JACCARD_GAIN_TARGET:.2f}")
    return current
