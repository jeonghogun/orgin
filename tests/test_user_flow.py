import pytest
from unittest.mock import patch, AsyncMock

from app.models.schemas import Room, ReviewMeta, Message

# Define a common set of mock services to patch across different API routes
MOCK_ROOM_STORAGE = patch("app.api.routes.rooms.storage_service", new_callable=AsyncMock)
MOCK_MSG_STORAGE = patch("app.api.routes.messages.storage_service", new_callable=AsyncMock)
MOCK_REVIEW_STORAGE = patch("app.api.routes.reviews.storage_service", new_callable=AsyncMock)
MOCK_REVIEW_SERVICE = patch("app.api.routes.reviews.review_service", new_callable=AsyncMock)
MOCK_LLM_SERVICE = patch("app.api.routes.messages.context_llm_service", new_callable=AsyncMock)


@MOCK_ROOM_STORAGE
@MOCK_MSG_STORAGE
@MOCK_REVIEW_STORAGE
@MOCK_REVIEW_SERVICE
@MOCK_LLM_SERVICE
class TestFullUserJourney:
    """
    Tests a simplified, mocked end-to-end user flow to ensure
    API endpoints are connected correctly.
    """

    def test_e2e_flow(self, mock_llm, mock_review_svc, mock_review_storage, mock_msg_storage, mock_room_storage, client):
        """
        Tests: Create Room -> Send Message -> Create Review -> Start Review
        """
        user_id = "test-user-e2e"
        room_id = "test-room-e2e"
        review_id = "test-review-e2e"

        # --- 1. Create Room ---
        mock_room_storage.get_rooms_by_owner.return_value = []
        mock_room_storage.create_room.return_value = Room(
            room_id=room_id, name="E2E Test Room", owner_id=user_id, type="main",
            created_at=123, updated_at=123, message_count=0
        )
        response = client.post("/api/rooms", json={"name": "E2E Test Room", "type": "main"})
        assert response.status_code == 200
        assert response.json()["room_id"] == room_id

        # --- 2. Send Message ---
        mock_msg_storage.get_room.return_value = Room(
            room_id=room_id, name="E2E Test Room", owner_id=user_id, type="main",
            created_at=123, updated_at=123, message_count=1
        )
        mock_msg_storage.get_messages.return_value = []
        mock_llm.invoke.return_value = "AI response"
        response = client.post(
            f"/api/rooms/{room_id}/messages",
            json={"content": "Hello, this is a test message."}
        )
        assert response.status_code == 200
        assert "ai_response" in response.json()["data"]
        mock_msg_storage.save_message.assert_called()

        # --- 3. Create Review ---
        mock_review_storage.get_room.return_value = Room(
            room_id=room_id, name="E2E Test Room", owner_id=user_id, type="sub",
            created_at=123, updated_at=123, message_count=1
        )
        mock_review_svc.create_review_and_start.return_value = ReviewMeta(
            review_id=review_id,
            room_id=room_id,
            topic="E2E Test",
            instruction="Test instruction",
            status="in_progress",
            total_rounds=3,
            current_round=0,
            created_at=123,
            failed_panels=[],
        )
        response = client.post(
            f"/api/rooms/{room_id}/reviews",
            json={"topic": "E2E Test", "instruction": "Test instruction"}
        )
        assert response.status_code == 200
        review_meta = ReviewMeta(**response.json())
        assert review_meta.review_id == review_id

        # --- 4. Start Review Generation ---
        mock_review_storage.get_review_meta.return_value = review_meta
        response = client.post(f"/api/reviews/{review_meta.review_id}/generate")
        assert response.status_code == 202
        assert response.json()["message"] == "Review generation started in the background."
        mock_review_svc.execute_review.assert_called_once_with(review_meta.review_id)
