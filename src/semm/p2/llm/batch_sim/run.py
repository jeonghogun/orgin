"""Batch simulation stub for P39 throughput targets."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

CACHE_HIT_TARGET = 0.30
THROUGHPUT_TARGET = 1000 / 60  # 1k requests under 60s


@dataclass
class SimulationResult:
    throughput: float
    cache_hit_rate: float
    duration: float


def run(requests: List[str], *, sleep: float = 0.0) -> SimulationResult:
    start = time.perf_counter()
    hits = 0
    for req in requests:
        if sleep:
            time.sleep(min(sleep, 0.001))
        if hash(req) % 10 < 3:
            hits += 1
    duration = time.perf_counter() - start
    throughput = len(requests) / max(duration, 1e-6)
    cache_hit_rate = hits / max(len(requests), 1)
    if throughput < THROUGHPUT_TARGET:
        print(f"[WARN] Throughput {throughput:.2f} req/s below target {THROUGHPUT_TARGET:.2f}")
    if cache_hit_rate < CACHE_HIT_TARGET:
        print(f"[WARN] Cache hit rate {cache_hit_rate:.2f} below target {CACHE_HIT_TARGET:.2f}")
    return SimulationResult(throughput=throughput, cache_hit_rate=cache_hit_rate, duration=duration)
