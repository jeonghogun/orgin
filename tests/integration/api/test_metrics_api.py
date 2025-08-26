import pytest
from fastapi.testclient import TestClient
from app.services.storage_service import storage_service
import time

def test_get_metrics_endpoint(authenticated_client: TestClient):
    """
    Tests the /metrics endpoint.
    """
    # --- 1. Setup: Create some dummy data ---
    # We need to create rooms and reviews first to satisfy foreign key constraints
    # Note: The test client is synchronous, so we don't use await here.
    # The underlying app calls are async and handled by the TestClient.
    main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for Metrics", "type": "main"})
    assert main_room_res.status_code == 200
    main_room_id = main_room_res.json()["room_id"]

    sub_room_res = authenticated_client.post(f"/api/rooms", json={"name": "Sub for Metrics", "type": "sub", "parent_id": main_room_id})
    assert sub_room_res.status_code == 200
    sub_room_id = sub_room_res.json()["room_id"]

    review_res = authenticated_client.post(f"/api/rooms/{sub_room_id}/reviews", json={"topic": "Metrics Topic", "instruction": "..."})
    assert review_res.status_code == 200
    review_id = review_res.json()["review_id"]

    # Now create the metrics directly in the DB for this test
    # In a full E2E test, we would let the review run.
    from app.models.schemas import ReviewMetrics
    metric1 = ReviewMetrics(
        review_id=review_id,
        total_duration_seconds=10.5,
        total_tokens_used=1000,
        total_cost_usd=0.002,
        round_metrics=[],
        created_at=int(time.time())
    )
    # The storage service methods are async, so we need to run them in an event loop
    import asyncio
    asyncio.run(storage_service.save_review_metrics(metric1))

    # --- 2. Call the endpoint ---
    response = authenticated_client.get("/api/metrics")
    assert response.status_code == 200

    data = response.json()
    assert "summary" in data
    assert "data" in data

    summary = data["summary"]
    assert summary["total_reviews"] == 1
    assert summary["avg_duration"] == 10.5
    assert summary["avg_tokens"] == 1000

    assert len(data["data"]) == 1
    assert data["data"][0]["review_id"] == review_id
