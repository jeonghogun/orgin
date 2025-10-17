"""Encoder modules for P32 macro-F1 ≥ 0.55 target."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

TARGET_MACRO_F1 = 0.55


@dataclass
class EncoderOutput:
    token_features: np.ndarray
    delta_features: np.ndarray
    line_features: np.ndarray


class DeltaEncoder:
    """Lightweight stub for joint text/delta encoding."""

    def __init__(self, hidden_dim: int = 16):
        self.hidden_dim = hidden_dim

    def __call__(self, tokens: np.ndarray, deltas: np.ndarray, lines: np.ndarray) -> EncoderOutput:
        token_features = tokens.mean(axis=-1, keepdims=True) * np.ones((tokens.shape[0], self.hidden_dim))
        delta_features = deltas.mean(axis=-1, keepdims=True) * np.ones((deltas.shape[0], self.hidden_dim))
        line_features = lines.mean(axis=-1, keepdims=True) * np.ones((lines.shape[0], self.hidden_dim))
        return EncoderOutput(token_features=token_features, delta_features=delta_features, line_features=line_features)


def evaluate_macro_f1(preds: np.ndarray, labels: np.ndarray) -> float:
    """Placeholder macro-F1 evaluation supporting acceptance checks."""

    preds_bin = (preds > 0.5).astype(int)
    labels_bin = (labels > 0.5).astype(int)
    tp = (preds_bin * labels_bin).sum(axis=0)
    fp = (preds_bin * (1 - labels_bin)).sum(axis=0)
    fn = ((1 - preds_bin) * labels_bin).sum(axis=0)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / np.maximum(tp + fn, 1)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-6)
    return float(np.nan_to_num(f1).mean())
