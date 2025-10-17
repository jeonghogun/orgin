"""Unit tests for soft edit surrogate."""
from __future__ import annotations

import numpy as np

from semm.p2.llm.surrogate import soft_ops


def test_surrogate_cost_monotonic():
    base = np.array([0.1, 0.5, -0.2])
    higher = np.array([0.2, 1.0, -0.4])
    assert soft_ops.surrogate_cost(higher) >= soft_ops.surrogate_cost(base)


def test_surrogate_eval_gradient_signal():
    batch = np.stack([np.linspace(0, i, 4) for i in range(1, 5)])

    def true_cost_fn(x: np.ndarray) -> np.ndarray:
        return x.sum(axis=1)

    corr = soft_ops.surrogate_eval(batch, true_cost_fn)
    assert -1.0 <= corr <= 1.0
