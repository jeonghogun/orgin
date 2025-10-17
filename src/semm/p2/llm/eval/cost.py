"""Cost evaluation stub (P37)."""
from __future__ import annotations

import numpy as np

COST_REDUCTION_TARGET = 0.10


def cost_reduction(baseline: np.ndarray, candidate: np.ndarray) -> float:
    if baseline.shape != candidate.shape:
        raise ValueError("Arrays must share the same shape")
    reduction = float((baseline - candidate).mean() / np.maximum(baseline.mean(), 1e-6))
    if reduction < COST_REDUCTION_TARGET:
        print(f"[WARN] Cost reduction {reduction:.3f} below target {COST_REDUCTION_TARGET:.2f}")
    return reduction
