import pytest
import time
import asyncio
from fastapi.testclient import TestClient
from app.models.schemas import ReviewMetrics
from app.services.storage_service import StorageService

@pytest.mark.asyncio
async def test_get_metrics_endpoint(authenticated_client: TestClient, storage_service: StorageService):
    """
    Tests the /metrics endpoint.
    This is an integration test and requires a running DB.
    """
    # --- 1. Setup: Create some dummy data ---
    # The TestClient's methods are synchronous, but they call an async app.
    # We use asyncio.to_thread to run these blocking calls in a non-blocking way.

    def setup_data():
        main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for Metrics", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        sub_room_res = authenticated_client.post(f"/api/rooms", json={"name": "Sub for Metrics", "type": "sub", "parent_id": main_room_id})
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        review_res = authenticated_client.post(f"/api/rooms/{sub_room_id}/reviews", json={"topic": "Metrics Topic", "instruction": "..."})
        assert review_res.status_code == 200
        return review_res.json()["review_id"]

    review_id = await asyncio.to_thread(setup_data)

    # Now create the metrics directly in the DB for this test
    metric1 = ReviewMetrics(
        review_id=review_id,
        total_duration_seconds=10.5,
        total_tokens_used=1000,
        total_cost_usd=0.002,
        round_metrics=[],
        created_at=int(time.time())
    )
    # Use the injected storage_service and run its sync method in a thread
    await asyncio.to_thread(storage_service.save_review_metrics, metric1)

    # --- 2. Call the endpoint ---
    response = await asyncio.to_thread(authenticated_client.get, "/api/metrics")
    assert response.status_code == 200

    data = response.json()
    assert "summary" in data
    assert "data" in data

    summary = data["summary"]
    assert summary["total_reviews"] >= 1 # Can't be sure it's exactly 1 if tests run in parallel
    assert "avg_duration" in summary
    assert "avg_tokens" in summary

    assert len(data["data"]) >= 1
    assert data["data"][0]["review_id"] == review_id
