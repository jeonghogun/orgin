"""Lightweight Celery tasks used for diagnostics and smoke tests.

These tasks intentionally avoid external dependencies so that the worker
pipeline can be validated in isolation during CI or local smoke testing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.diagnostic_tasks.generate_smoke_payload")
def generate_smoke_payload(seed: int = 1) -> Dict[str, object]:
    """Return a deterministic payload used by the smoke workflow."""

    values = [seed, seed * 2, seed * 3]
    return {
        "seed": seed,
        "created_at": datetime.utcnow().isoformat(),
        "values": values,
        "total": sum(values),
    }


@celery_app.task(name="app.tasks.diagnostic_tasks.evaluate_smoke_payload")
def evaluate_smoke_payload(payload: Dict[str, object]) -> Dict[str, object]:
    """Validate the payload emitted by :func:`generate_smoke_payload`."""

    values = payload.get("values", [])
    total = sum(values) if isinstance(values, list) else payload.get("total", 0)
    return {
        "status": "ok" if total >= payload.get("seed", 0) else "error",
        "total": total,
        "count": len(values),
        "seed": payload.get("seed"),
    }

