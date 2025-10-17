"""Soft edit operations for the differentiable surrogate (P31)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np

TARGET_CORRELATION = 0.80  # Pearson r ≥ 0.80 vs. true costs


@dataclass
class SoftEditResult:
    cost: float
    details: Tuple[float, float, float, float]


def _softmax(logits: np.ndarray, tau: float) -> np.ndarray:
    scaled = logits / max(tau, 1e-6)
    exps = np.exp(scaled - scaled.max())
    return exps / exps.sum()


def soft_insert(delta: np.ndarray, tau: float = 0.1) -> SoftEditResult:
    """Soft insert operation returning surrogate cost."""

    weights = _softmax(delta, tau)
    cost = float(np.dot(weights, np.arange(delta.size)))
    return SoftEditResult(cost=cost, details=(weights.mean(), weights.var(), tau, delta.sum()))


def soft_delete(delta: np.ndarray, tau: float = 0.1) -> SoftEditResult:
    weights = _softmax(-delta, tau)
    cost = float(np.dot(weights, np.arange(delta.size)[::-1]))
    return SoftEditResult(cost=cost, details=(weights.mean(), weights.var(), tau, delta.sum()))


def soft_substitute(delta: np.ndarray, tau: float = 0.1) -> SoftEditResult:
    weights = _softmax(np.abs(delta), tau)
    cost = float(np.dot(weights, np.abs(delta)))
    return SoftEditResult(cost=cost, details=(weights.mean(), weights.var(), tau, float(np.abs(delta).sum())))


def soft_reorder(delta: np.ndarray, tau: float = 0.1) -> SoftEditResult:
    order = np.argsort(delta)
    weights = _softmax(delta[order], tau)
    cost = float(np.dot(weights, order))
    return SoftEditResult(cost=cost, details=(weights.mean(), weights.var(), tau, float(order.sum())))


def surrogate_cost(delta: np.ndarray, tau: float = 0.1) -> float:
    """Aggregate surrogate cost using all edit operations."""

    inserts = soft_insert(delta, tau).cost
    deletes = soft_delete(delta, tau).cost
    substitutes = soft_substitute(delta, tau).cost
    reorders = soft_reorder(delta, tau).cost
    return float(inserts + deletes + substitutes + reorders)


def pearson_r(x: np.ndarray, y: np.ndarray) -> float:
    if x.size != y.size:
        raise ValueError("Inputs must have equal length")
    x_mean = x.mean()
    y_mean = y.mean()
    numerator = np.sum((x - x_mean) * (y - y_mean))
    denominator = math.sqrt(np.sum((x - x_mean) ** 2) * np.sum((y - y_mean) ** 2))
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def surrogate_eval(delta_batch: np.ndarray, true_cost_fn: Callable[[np.ndarray], np.ndarray]) -> float:
    """Evaluate correlation between surrogate cost and provided true cost function."""

    surrogate_values = np.array([surrogate_cost(d) for d in delta_batch])
    true_values = true_cost_fn(delta_batch)
    corr = pearson_r(surrogate_values, true_values)
    if corr < TARGET_CORRELATION:
        print(
            f"[WARN] Surrogate correlation {corr:.3f} below target {TARGET_CORRELATION:.2f}."
        )
    else:
        print(f"[OK] Surrogate correlation {corr:.3f} meets target {TARGET_CORRELATION:.2f}.")
    return corr
