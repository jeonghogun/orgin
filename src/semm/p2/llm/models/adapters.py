"""Adapter utilities for initializing encoders from SBERT (placeholder)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class AdapterConfig:
    hidden_dim: int = 16
    freeze_base: bool = False


def initialize_with_sbert(encoder: Any, config: AdapterConfig) -> Any:
    """Pretend to initialize encoder weights from SBERT checkpoints."""

    if hasattr(encoder, "hidden_dim"):
        encoder.hidden_dim = config.hidden_dim
    setattr(encoder, "initialized_from_sbert", True)
    return encoder


def project_embeddings(embeddings: np.ndarray, config: AdapterConfig) -> np.ndarray:
    """Project embeddings to target dimension."""

    if embeddings.ndim != 2:
        raise ValueError("Embeddings must be 2D")
    scale = config.hidden_dim / max(embeddings.shape[1], 1)
    return embeddings * scale
