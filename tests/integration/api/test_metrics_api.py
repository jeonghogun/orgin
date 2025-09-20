from fastapi.testclient import TestClient
import time


def test_get_metrics_endpoint(authenticated_client: TestClient, test_data_builder):
    """
    Tests the /metrics endpoint.
    """
    # --- 1. Setup: Create some dummy data via the scenario builder ---
    main_room = test_data_builder.ensure_main_room("Metrics Main")
    sub_room = test_data_builder.create_sub_room("Sub for Metrics", parent_id=main_room.room_id)
    review = test_data_builder.create_review(sub_room.room_id, topic="Metrics Topic", instruction="...")

    # Now create the metrics directly in the DB for this test
    # In a full E2E test, we would let the review run.
    from app.models.schemas import ReviewMetrics
    metric1 = ReviewMetrics(
        review_id=review.review_id,
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
        if review_data["review_id"] == review.review_id:
            our_review = review_data
            break

    assert our_review is not None, f"Review {review.review_id} not found in metrics data"
    assert our_review["total_duration_seconds"] == 10.5
    assert our_review["total_tokens_used"] == 1000
