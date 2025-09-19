"""Unit tests for :mod:`app.services.kpi_service`."""

import json
from datetime import date
from typing import Any, Dict, List, Tuple

import pytest

from app.services.kpi_service import KPIService


class _FakeDatabaseService:
    """Minimal fake that mimics the database service interface."""

    def __init__(self) -> None:
        self.updates: List[Tuple[str, Tuple[Any, ...]]] = []
        self.query_results: List[Dict[str, Any]] = []
        self.query_calls: List[Tuple[str, Tuple[Any, ...]]] = []

    def execute_update(self, query: str, params: Tuple[Any, ...]) -> int:  # pragma: no cover - trivial
        self.updates.append((query, params))
        return 1

    def execute_query(self, query: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:  # pragma: no cover - trivial
        self.query_calls.append((query, params))
        return self.query_results


@pytest.mark.asyncio
async def test_save_snapshot_serializes_details() -> None:
    fake_db = _FakeDatabaseService()
    service = KPIService(fake_db)

    await service.save_snapshot(date(2024, 1, 2), "metric", 12.5, {"foo": "bar"})

    assert fake_db.updates, "save_snapshot should emit a database write"
    _, params = fake_db.updates[0]
    assert params[:3] == (date(2024, 1, 2), "metric", 12.5)
    assert json.loads(params[3]) == {"foo": "bar"}


@pytest.mark.asyncio
async def test_get_historical_kpis_pivots_results() -> None:
    fake_db = _FakeDatabaseService()
    fake_db.query_results = [
        {"snapshot_date": date(2024, 1, 1), "metric_name": "daily", "value": 10.0},
        {"snapshot_date": date(2024, 1, 2), "metric_name": "daily", "value": 15.5},
        {"snapshot_date": date(2024, 1, 2), "metric_name": "weekly", "value": 99.9},
    ]
    service = KPIService(fake_db)

    data = await service.get_historical_kpis(date(2024, 1, 1), date(2024, 1, 5))

    assert set(data.keys()) == {"daily", "weekly"}
    assert data["daily"]["dates"] == ["2024-01-01", "2024-01-02"]
    assert data["daily"]["values"] == [10.0, 15.5]
    assert data["weekly"]["dates"] == ["2024-01-02"]
    assert data["weekly"]["values"] == [99.9]

