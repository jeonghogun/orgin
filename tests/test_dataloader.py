"""Tests for SEMM LLM dataloader scaffolding."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from semm.p2.llm.data import build


def test_build_dataset_handles_missing_files(tmp_path: Path) -> None:
    dataset = build.build_dataset({
        "parsed": tmp_path / "parsed.jsonl",
        "deltas": tmp_path / "deltas.jsonl",
        "lines": tmp_path / "lines.jsonl",
        "surface": tmp_path / "surface.jsonl",
    })
    assert len(dataset) == 0


def test_next_or_default_returns_empty_dict() -> None:
    assert build.next_or_default(iter(())) == {}
