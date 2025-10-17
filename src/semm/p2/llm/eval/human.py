"""Human evaluation harness placeholder (P38)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

KAPPA_TARGET = 0.60


@dataclass
class HumanRating:
    rater_id: str
    score: float


def aggregate_ratings(ratings: List[HumanRating]) -> float:
    if not ratings:
        return 0.0
    mean_score = sum(r.score for r in ratings) / len(ratings)
    if mean_score < KAPPA_TARGET:
        print(f"[WARN] Human agreement {mean_score:.2f} below target {KAPPA_TARGET:.2f}")
    return mean_score
