import pytest
from unittest.mock import MagicMock, patch

from app.services.storage_service import StorageService
from app.models.schemas import Room, Message, ReviewMeta

@pytest.fixture
def mock_db_service():
    """Fixture for a mocked DatabaseService."""
    return MagicMock()

@pytest.fixture
def mock_secret_provider():
    """Fixture for a mocked SecretProvider."""
    mock = MagicMock()
    mock.get.return_value = "fake-key-for-testing"
    return mock

@pytest.fixture
def storage_service(mock_db_service, mock_secret_provider):
    """Fixture for StorageService with mocked dependencies."""
    with patch('app.services.storage_service.get_database_service', return_value=mock_db_service):
        service = StorageService(secret_provider=mock_secret_provider)
        yield service

class TestStorageServiceWithDB:
    """Test Storage Service with a mocked DatabaseService."""

    def test_create_room(self, storage_service, mock_db_service):
        """Test creating a room calls the database correctly."""
        room_id = "test-room-db"
        storage_service.create_room(room_id, "DB Room", "db-user", "main")
        
        mock_db_service.execute_update.assert_called_once()
        query = mock_db_service.execute_update.call_args[0][0]
        assert "INSERT INTO rooms" in query

    def test_get_room(self, storage_service, mock_db_service):
        """Test getting a room calls the database and handles results."""
        room_id = "test-room-db"
        mock_db_service.execute_query.return_value = [{
            "room_id": room_id, "name": "DB Room", "owner_id": "db-user",
            "type": "main", "parent_id": None, "created_at": 1, "updated_at": 1, "message_count": 0
        }]
        
        room = storage_service.get_room(room_id)
        
        assert room is not None
        assert isinstance(room, Room)
        assert room.room_id == room_id
        mock_db_service.execute_query.assert_called_once_with(
            "SELECT * FROM rooms WHERE room_id = %s", (room_id,)
        )

    def test_get_room_not_found(self, storage_service, mock_db_service):
        """Test getting a non-existent room."""
        mock_db_service.execute_query.return_value = []
        room = storage_service.get_room("non-existent")
        assert room is None

    def test_save_message(self, storage_service, mock_db_service):
        """Test saving a message calls the database twice (insert and update)."""
        msg = Message(message_id="msg-db", room_id="room-db", user_id="user-db", content="Hello DB", timestamp=123, role="user")
        storage_service.save_message(msg)
        
        assert mock_db_service.execute_update.call_count == 2
        first_call_query = mock_db_service.execute_update.call_args_list[0].args[0]
        assert "INSERT INTO messages" in first_call_query
        second_call_query = mock_db_service.execute_update.call_args_list[1].args[0]
        assert "UPDATE rooms SET message_count" in second_call_query

    def test_get_messages(self, storage_service, mock_db_service):
        """Test getting messages for a room."""
        room_id = "room-db"
        mock_db_service.execute_query.return_value = [
            {"message_id": "msg-1", "room_id": room_id, "user_id": "user-1", "content": "Msg 1", "timestamp": 1, "role": "user"},
            {"message_id": "msg-2", "room_id": room_id, "user_id": "user-2", "content": "Msg 2", "timestamp": 2, "role": "user"}
        ]
        
        messages = storage_service.get_messages(room_id)
        
        assert len(messages) == 2
        assert all(isinstance(m, Message) for m in messages)

        expected_query = """
            SELECT message_id, room_id, user_id, role,
                   pgp_sym_decrypt(content, %s) as content,
                   timestamp
            FROM messages
            WHERE room_id = %s
            ORDER BY timestamp ASC
        """
        mock_db_service.execute_query.assert_called_once()
        called_query = mock_db_service.execute_query.call_args.args[0]
        assert " ".join(called_query.split()) == " ".join(expected_query.split())


    def test_save_review_meta(self, storage_service, mock_db_service):
        """Test saving review metadata."""
        review_meta = ReviewMeta(
            review_id="review-db", room_id="room-db", topic="DB Topic", instruction="DB Instruction",
            status="in_progress", total_rounds=3, current_round=1, created_at=123
        )
        storage_service.save_review_meta(review_meta)
        
        mock_db_service.execute_update.assert_called_once()
        query = mock_db_service.execute_update.call_args[0][0]
        assert "INSERT INTO reviews" in query

    def test_get_review_meta(self, storage_service, mock_db_service):
        """Test getting review metadata."""
        review_id = "review-db"
        mock_db_service.execute_query.return_value = [{
            "review_id": review_id, "room_id": "room-db", "topic": "DB Topic", "instruction": "DB Instruction",
            "status": "in_progress", "total_rounds": 3, "current_round": 1, "created_at": 123, "completed_at": None
        }]
        
        review_meta = storage_service.get_review_meta(review_id)
        
        assert review_meta is not None
        assert isinstance(review_meta, ReviewMeta)
        assert review_meta.review_id == review_id

        expected_query = """
            SELECT
                review_id,
                room_id,
                topic,
                instruction,
                status,
                total_rounds,
                current_round,
                created_at,
                completed_at
            FROM reviews
            WHERE review_id = %s
        """
        mock_db_service.execute_query.assert_called_once()
        called_query = mock_db_service.execute_query.call_args.args[0]
        called_params = mock_db_service.execute_query.call_args.args[1]

        assert " ".join(called_query.split()) == " ".join(expected_query.split())
        assert called_params == (review_id,)

    def test_log_review_event(self, storage_service, mock_db_service):
        """Test logging a review event."""
        event_data = {
            "review_id": "review-db", "ts": 12345, "type": "test_event",
            "round": 1, "actor": "tester", "content": "Testing event logging."
        }
        storage_service.log_review_event(event_data)

        mock_db_service.execute_update.assert_called_once()
        query = mock_db_service.execute_update.call_args[0][0]
        assert "INSERT INTO review_events" in query
