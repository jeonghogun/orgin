import pytest
from unittest.mock import patch, AsyncMock

from app.models.schemas import Room, ReviewMeta
from tests.conftest import USER_ID

class TestE2EReviewFlow:
    """End-to-end tests for the full review workflow."""

    @pytest.mark.anyio
    @patch("app.api.routes.rooms.storage_service", new_callable=AsyncMock)
    @patch("app.api.routes.reviews.storage_service", new_callable=AsyncMock)
    @patch("app.api.routes.reviews.review_service", new_callable=AsyncMock)
    async def test_full_review_workflow(self, mock_review_service, mock_review_storage, mock_room_storage, authenticated_client):
        """
        Simulates an API-level E2E flow for creating a review and triggering it.
        """
        client = authenticated_client

        # --- Mock Service Layer ---
        main_room_id = "main-e2e"
        sub_room_id = "sub-e2e"
        review_id = "review-e2e"

        # Mocks for room creation
        mock_room_storage.get_rooms_by_owner.return_value = []
        mock_room_storage.get_room.return_value = Room(room_id=main_room_id, name="My Main", owner_id=USER_ID, type="main", created_at=1, updated_at=1, message_count=0)
        mock_room_storage.create_room.side_effect = [
            Room(room_id=main_room_id, name="My Main", owner_id=USER_ID, type="main", created_at=1, updated_at=1, message_count=0),
            Room(room_id=sub_room_id, name="My Project", owner_id=USER_ID, type="sub", parent_id=main_room_id, created_at=2, updated_at=2, message_count=0)
        ]

        # Mocks for review creation
        mock_review_storage.get_room.return_value = Room(room_id=sub_room_id, name="My Project", owner_id=USER_ID, type="sub", parent_id=main_room_id, created_at=2, updated_at=2, message_count=0)
        mock_review_storage.save_review_meta.return_value = None

        # Mock for triggering the review
        mock_review_service.execute_review = AsyncMock()

        # --- API Calls ---
        # 1. Create Main Room
        response = client.post("/api/rooms", json={"name": "My Main", "type": "main"})
        assert response.status_code == 200
        main_room = Room(**response.json())

        # 2. Create Sub Room
        response = client.post("/api/rooms", json={"name": "My Project", "type": "sub", "parent_id": main_room.room_id})
        assert response.status_code == 200
        sub_room = Room(**response.json())

        # 3. Create a Review
        review_payload = {"topic": "Future of AI", "instruction": "Analyze pros and cons."}
        response = client.post(f"/api/rooms/{sub_room.room_id}/reviews", json=review_payload)
        assert response.status_code == 200
        review_meta = ReviewMeta(**response.json())

        # 4. Trigger the Review process
        response = client.post(f"/api/reviews/{review_meta.review_id}/generate")
        assert response.status_code == 200

        # 5. Verify the background task was called
        mock_review_service.execute_review.assert_called_once_with(review_meta.review_id)
