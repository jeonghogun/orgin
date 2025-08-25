import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.storage_service import StorageService
from app.models.schemas import Room, Message, ReviewMeta

@pytest.fixture
def mock_db_service():
    """Fixture for a mocked DatabaseService."""
    return AsyncMock()

@pytest.fixture
def storage_service(mock_db_service):
    """Fixture for StorageService with a mocked database."""
    with patch('app.services.storage_service.get_database_service', return_value=mock_db_service):
        service = StorageService()
        yield service

@pytest.mark.asyncio
class TestStorageServiceWithDB:
    """Test Storage Service with a mocked DatabaseService."""

    async def test_create_room(self, storage_service, mock_db_service):
        """Test creating a room calls the database correctly."""
        room_id = "test-room-db"
        await storage_service.create_room(room_id, "DB Room", "db-user", "main")
        
        mock_db_service.execute_update.assert_called_once()
        query = mock_db_service.execute_update.call_args[0][0]
        assert "INSERT INTO rooms" in query

    async def test_get_room(self, storage_service, mock_db_service):
        """Test getting a room calls the database and handles results."""
        room_id = "test-room-db"
        mock_db_service.execute_query.return_value = [{
            "room_id": room_id, "name": "DB Room", "owner_id": "db-user",
            "type": "main", "parent_id": None, "created_at": 1, "updated_at": 1, "message_count": 0
        }]
        
        room = await storage_service.get_room(room_id)
        
        assert room is not None
        assert isinstance(room, Room)
        assert room.room_id == room_id
        mock_db_service.execute_query.assert_called_once_with(
            "SELECT * FROM rooms WHERE room_id = %s", (room_id,)
        )

    async def test_get_room_not_found(self, storage_service, mock_db_service):
        """Test getting a non-existent room."""
        mock_db_service.execute_query.return_value = []
        room = await storage_service.get_room("non-existent")
        assert room is None

    async def test_save_message(self, storage_service, mock_db_service):
        """Test saving a message calls the database."""
        msg = Message(message_id="msg-db", room_id="room-db", user_id="user-db", content="Hello DB", timestamp=123, role="user")
        await storage_service.save_message(msg)
        
        mock_db_service.execute_update.assert_called_once()
        query = mock_db_service.execute_update.call_args[0][0]
        assert "INSERT INTO messages" in query

    async def test_get_messages(self, storage_service, mock_db_service):
        """Test getting messages for a room."""
        room_id = "room-db"
        mock_db_service.execute_query.return_value = [
            {"message_id": "msg-1", "room_id": room_id, "user_id": "user-1", "content": "Msg 1", "timestamp": 1, "role": "user"},
            {"message_id": "msg-2", "room_id": room_id, "user_id": "user-2", "content": "Msg 2", "timestamp": 2, "role": "user"}
        ]
        
        messages = await storage_service.get_messages(room_id)
        
        assert len(messages) == 2
        assert all(isinstance(m, Message) for m in messages)
        mock_db_service.execute_query.assert_called_once_with(
            "SELECT * FROM messages WHERE room_id = %s ORDER BY timestamp ASC", (room_id,)
        )

    async def test_save_review_meta(self, storage_service, mock_db_service):
        """Test saving review metadata."""
        review_meta = ReviewMeta(
            review_id="review-db", room_id="room-db", topic="DB Topic", instruction="DB Instruction",
            status="in_progress", total_rounds=3, current_round=1, created_at=123
        )
        await storage_service.save_review_meta(review_meta)
        
        mock_db_service.execute_update.assert_called_once()
        query = mock_db_service.execute_update.call_args[0][0]
        assert "INSERT INTO reviews" in query

    async def test_get_review_meta(self, storage_service, mock_db_service):
        """Test getting review metadata."""
        review_id = "review-db"
        mock_db_service.execute_query.return_value = [{
            "review_id": review_id, "room_id": "room-db", "topic": "DB Topic", "instruction": "DB Instruction",
            "status": "in_progress", "total_rounds": 3, "current_round": 1, "created_at": 123
        }]
        
        review_meta = await storage_service.get_review_meta(review_id)
        
        assert review_meta is not None
        assert isinstance(review_meta, ReviewMeta)
        assert review_meta.review_id == review_id
        mock_db_service.execute_query.assert_called_once_with(
            "SELECT * FROM reviews WHERE review_id = %s", (review_id,)
        )

    async def test_log_review_event(self, storage_service, mock_db_service):
        """Test logging a review event."""
        event_data = {
            "review_id": "review-db", "ts": 12345, "type": "test_event",
            "round": 1, "actor": "tester", "content": "Testing event logging."
        }
        await storage_service.log_review_event(event_data)

        mock_db_service.execute_update.assert_called_once()
        query = mock_db_service.execute_update.call_args[0][0]
        assert "INSERT INTO review_events" in query
