"""Tests for encoder/decoder stubs."""
from __future__ import annotations

import numpy as np

from semm.p2.llm.models import dec_linehead, enc_delta
from semm.p2.llm.train_loop import train_loop, TrainConfig


def test_encoder_output_shapes():
    encoder = enc_delta.DeltaEncoder(hidden_dim=8)
    tokens = np.ones((2, 4))
    deltas = np.ones((2, 4))
    lines = np.ones((2, 4))
    output = encoder(tokens, deltas, lines)
    assert output.token_features.shape == (2, 8)
    assert output.delta_features.shape == (2, 8)
    assert output.line_features.shape == (2, 8)


def test_train_loop_returns_metrics():
    batch = {
        "tokens": np.ones((2, 4)),
        "deltas": np.ones((2, 4)),
        "lines": np.ones((2, 4)),
        "labels": np.ones((2, 1)),
        "costs": np.ones((2, 1)),
    }
    metrics = train_loop(TrainConfig(), batch)
    assert "macro_f1" in metrics
    assert "cost_mape" in metrics
