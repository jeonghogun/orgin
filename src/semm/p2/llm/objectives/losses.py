"""Core loss stubs for joint training."""
from __future__ import annotations

import numpy as np


def multilabel_bce(logits: np.ndarray, labels: np.ndarray) -> float:
    probs = 1 / (1 + np.exp(-logits))
    loss = -(labels * np.log(probs + 1e-9) + (1 - labels) * np.log(1 - probs + 1e-9))
    return float(loss.mean())


def cost_regression_loss(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.square(pred - target).mean())
