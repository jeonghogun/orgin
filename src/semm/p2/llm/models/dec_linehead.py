"""Decoder heads for P33 Δ-F1 and cost targets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

TARGET_DELTA_F1 = 0.60
TARGET_COST_MAPE = 0.20


@dataclass
class HeadOutput:
    delta_logits: np.ndarray
    cost_pred: np.ndarray


class LineDecoderHead:
    def __init__(self, hidden_dim: int = 16):
        self.hidden_dim = hidden_dim

    def __call__(self, encoder_features: np.ndarray) -> HeadOutput:
        logits = encoder_features.mean(axis=-1, keepdims=True)
        cost = encoder_features.var(axis=-1, keepdims=True)
        return HeadOutput(delta_logits=logits, cost_pred=cost)


def mean_absolute_percentage_error(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean(np.abs((target - pred) / np.maximum(target, 1e-6))))
