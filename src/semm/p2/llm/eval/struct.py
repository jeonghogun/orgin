"""Structural evaluation stub (P36)."""
from __future__ import annotations

import numpy as np

DELTA_PHI_TARGET = 0.05
VIOLATION_TARGET = 0.005


def delta_phi_gain(values: np.ndarray) -> float:
    gain = float(values.mean())
    if gain < DELTA_PHI_TARGET:
        print(f"[WARN] Δφ gain {gain:.3f} below target {DELTA_PHI_TARGET:.2f}")
    return gain


def violation_rate(violations: np.ndarray) -> float:
    rate = float(violations.mean())
    if rate > VIOLATION_TARGET:
        print(f"[WARN] Guardrail violations {rate:.3f} exceed target {VIOLATION_TARGET:.3f}")
    return rate
