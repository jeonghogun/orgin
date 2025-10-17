"""Geometric regularizers for curvature and length (P33)."""
from __future__ import annotations

import numpy as np


def curvature_penalty(line_steps: np.ndarray) -> float:
    if line_steps.size == 0:
        return 0.0
    diffs = np.diff(line_steps, axis=0)
    return float(np.square(diffs).mean())


def length_penalty(line_steps: np.ndarray) -> float:
    if line_steps.size == 0:
        return 0.0
    distances = np.linalg.norm(np.diff(line_steps, axis=0), axis=-1)
    return float(distances.sum())
