from fastapi.testclient import TestClient

from app.api.dependencies import get_storage_service
from app.services.review_service import ReviewService


def test_review_status_endpoint_returns_history(authenticated_client: TestClient, test_data_builder):
    main_room = test_data_builder.ensure_main_room("Status Main")
    sub_room = test_data_builder.create_sub_room("Status Sub", parent_id=main_room.room_id)
    review = test_data_builder.create_review(
        sub_room.room_id,
        topic="Status Topic",
        instruction="Track the async pipeline",
    )

    storage = get_storage_service()
    review_service = ReviewService(storage)

    review_service.record_status_event(review.review_id, "queued")
    review_service.record_status_event(review.review_id, "fallback_started")
    review_service.record_status_event(review.review_id, "fallback_finished")
    storage.update_review(review.review_id, {"status": "in_progress"})

    response = authenticated_client.get(f"/api/reviews/{review.review_id}/status")
    assert response.status_code == 200

    payload = response.json()
    assert payload["review_id"] == review.review_id
    assert payload["status"] == "in_progress"
    assert payload["fallback_active"] is True
    assert payload["status_history"][-1]["status"] == "fallback_finished"
    assert payload["status_history"][0]["status"] == "queued"
