from fastapi.testclient import TestClient
import time

def test_get_metrics_endpoint(authenticated_client: TestClient):
    """
    Tests the /metrics endpoint.
    """
    # --- 0. Clean up any existing test data ---
    from app.api.dependencies import get_database_service
    db_service = get_database_service()
    
    # Clean up existing review metrics and related data
    db_service.execute_update("DELETE FROM review_metrics")
    db_service.execute_update("DELETE FROM reviews")
    db_service.execute_update("DELETE FROM rooms WHERE room_id LIKE 'room_%'")
    
    # --- 1. Setup: Create some dummy data ---
    # We need to create rooms and reviews first to satisfy foreign key constraints
    # Note: The test client is synchronous, so we don't use await here.
    # The underlying app calls are async and handled by the TestClient.
    # Ensure we have a main room to attach sub-rooms to
    main_room_res = authenticated_client.post(
        "/api/rooms",
        json={"name": "Metrics Main", "type": "main", "parent_id": None},
    )
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
    # Save the review metrics
    from app.api.dependencies import get_storage_service
    storage_service = get_storage_service()
    storage_service.save_review_metrics(metric1)

    # --- 2. Call the endpoint ---
    response = authenticated_client.get("/api/metrics")
    assert response.status_code == 200

    data = response.json()
    assert "summary" in data
    assert "data" in data

    summary = data["summary"]
    # Check that we have at least 1 review (our test review)
    assert summary["total_reviews"] >= 1
    
    # Find our specific review in the data
    our_review = None
    for review_data in data["data"]:
        if review_data["review_id"] == review_id:
            our_review = review_data
            break
    
    assert our_review is not None, f"Review {review_id} not found in metrics data"
    assert our_review["total_duration_seconds"] == 10.5
    assert our_review["total_tokens_used"] == 1000
