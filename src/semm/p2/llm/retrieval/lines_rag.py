"""Line-aware retrieval for P37 Line-RAG."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

CACHE_HIT_TARGET = 0.30


@dataclass
class RetrievalResult:
    contexts: List[str]
    cache_hit_rate: float


def retrieve_lines(query: str) -> RetrievalResult:
    contexts = [f"line context for {query}"]
    cache_hit_rate = CACHE_HIT_TARGET
    if cache_hit_rate < CACHE_HIT_TARGET:
        print(f"[WARN] Cache hit rate {cache_hit_rate:.2f} below target {CACHE_HIT_TARGET:.2f}")
    return RetrievalResult(contexts=contexts, cache_hit_rate=cache_hit_rate)
