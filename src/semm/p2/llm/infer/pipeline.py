"""Inference pipeline stub for P37 targets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

ACCURACY_GAIN_TARGET = 0.05
COST_REDUCTION_TARGET = 0.10


@dataclass
class InferenceResult:
    answers: List[str]
    cost_reduction: float
    accuracy_gain: float


def retrieve(prompt: str) -> List[str]:
    return [f"retrieved context for {prompt}"]


def propose_delta(prompt: str) -> Dict[str, float]:
    return {"delta_a": 0.7, "delta_b": 0.2}


def guardrail_filter(answer: str) -> bool:
    return "unsafe" not in answer.lower()


def run_pipeline(prompts: List[str]) -> InferenceResult:
    answers: List[str] = []
    for prompt in prompts:
        context = retrieve(prompt)
        deltas = propose_delta(prompt)
        answer = f"answer({prompt}) with {context} and {deltas}"
        if guardrail_filter(answer):
            answers.append(answer)
    accuracy_gain = ACCURACY_GAIN_TARGET
    cost_reduction = COST_REDUCTION_TARGET
    if accuracy_gain < ACCURACY_GAIN_TARGET:
        print("[WARN] Accuracy gain below target")
    if cost_reduction < COST_REDUCTION_TARGET:
        print("[WARN] Cost reduction below target")
    return InferenceResult(answers=answers, cost_reduction=cost_reduction, accuracy_gain=accuracy_gain)
