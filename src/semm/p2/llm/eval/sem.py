"""Semantic evaluation stub (P34, P38)."""
from __future__ import annotations

import numpy as np

SEMANTIC_TARGET = 0.05
KAPPA_TARGET = 0.60


def semantic_improvement(current: float) -> float:
    if current < SEMANTIC_TARGET:
        print(f"[WARN] Semantic improvement {current:.3f} below target {SEMANTIC_TARGET:.2f}")
    return current


def human_kappa(scores: np.ndarray) -> float:
    if scores.size == 0:
        return 0.0
    kappa = float(scores.mean())
    if kappa < KAPPA_TARGET:
        print(f"[WARN] Human agreement κ={kappa:.2f} below target {KAPPA_TARGET:.2f}")
    return kappa
