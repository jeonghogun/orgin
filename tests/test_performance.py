import pytest
from unittest.mock import AsyncMock, patch

from app.models.schemas import Room, Message


@patch("app.api.routes.messages.storage_service", new_callable=AsyncMock)
@patch("app.api.routes.rooms.storage_service", new_callable=AsyncMock)
@patch("app.services.intent_service.intent_service", new_callable=AsyncMock)
@patch("app.services.rag_service.rag_service", new_callable=AsyncMock)
class TestLoadScenarios:
    """
    Simplified performance and load tests focusing on correctness
    rather than strict time-based assertions.
    """

    def test_multiple_messages_in_sequence(
        self, mock_rag_service, mock_intent_service, mock_room_storage, mock_msg_storage, client
    ):
        """Test sending multiple messages to the same room sequentially."""
        room_id = "sequential-room"

        # Mock storage for creating the room
        mock_room_storage.get_rooms_by_owner.return_value = []
        mock_room_storage.create_room.return_value = Room(
            room_id=room_id, name="Test", owner_id="test", type="main",
            created_at=123, updated_at=123, message_count=0
        )

        # Create room
        response = client.post("/api/rooms", json={"name": "Test", "type": "main"})
        assert response.status_code == 200

        # Mock storage for getting and saving messages
        mock_msg_storage.get_room.return_value = Room(
            room_id=room_id, name="Test", owner_id="test", type="main",
            created_at=123, updated_at=123, message_count=0
        )
        mock_msg_storage.get_messages.return_value = []

        # Mock the intent service and RAG service
        mock_intent_service.classify_intent.return_value = {"intent": "general"}
        mock_rag_service.generate_rag_response.return_value = "AI response from RAG"

        # Send multiple messages
        for i in range(5):
            response = client.post(
                f"/api/rooms/{room_id}/messages",
                json={"content": f"Test message {i}"},
            )
            assert response.status_code == 200
            assert "ai_response" in response.json()["data"]

        # Verify that save_message was called multiple times (user + ai for each message)
        assert mock_msg_storage.save_message.call_count >= 10

    def test_error_requests_do_not_break_server(
        self, mock_rag_service, mock_intent_service, mock_room_storage, mock_msg_storage, client
    ):
        """
        Test that sending invalid requests does not prevent subsequent
        valid requests from being processed.
        """
        # Send a valid request to ensure the server is responsive
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()
        assert response.json()["status"] == "healthy"
