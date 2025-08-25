import pytest
from unittest.mock import patch, MagicMock

from app.models.schemas import Room
from tests.conftest import USER_ID

@patch("app.api.routes.rooms.storage_service.db", new_callable=MagicMock)
class TestRoomHierarchy:
    """Tests for room creation and hierarchy rules with mocked DB."""

    def test_create_main_room_success(self, mock_db, authenticated_client):
        """Test creating a main room successfully."""
        mock_db.execute_query.return_value = []  # No existing main room

        response = authenticated_client.post("/api/rooms", json={"name": "My Main Room", "type": "main"})

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "main"
        assert data["owner_id"] == USER_ID
        mock_db.execute_query.assert_called_once()
        mock_db.execute_update.assert_called_once()

    def test_create_main_room_fails_if_already_exists(self, mock_db, authenticated_client):
        """A user cannot create more than one main room."""
        mock_db.execute_query.return_value = [{'type': 'main'}] # Simulate existing main room

        response = authenticated_client.post("/api/rooms", json={"name": "New Main", "type": "main"})

        assert response.status_code == 400
        assert "Main room already exists" in response.json()["detail"]

    def test_create_sub_room_success(self, mock_db, authenticated_client):
        """Test creating a sub room successfully."""
        main_room_data = {"room_id": "main-1", "name": "Main", "owner_id": USER_ID, "type": "main", "created_at": 1, "updated_at": 1, "message_count": 0}
        mock_db.execute_query.return_value = [main_room_data] # Mock the parent room fetch

        response = authenticated_client.post("/api/rooms", json={"name": "My Sub Room", "type": "sub", "parent_id": "main-1"})

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "sub"
        assert data["parent_id"] == "main-1"
        mock_db.execute_query.assert_called_once() # For getting the parent
        mock_db.execute_update.assert_called_once() # For creating the new sub-room

    def test_create_sub_room_fails_with_invalid_parent_type(self, mock_db, authenticated_client):
        """Test creating a sub room fails if the parent is not a main room."""
        not_main_room_data = {"room_id": "sub-1", "name": "Another Sub", "owner_id": USER_ID, "type": "sub", "created_at": 1, "updated_at": 1, "message_count": 0}
        mock_db.execute_query.return_value = [not_main_room_data]

        response = authenticated_client.post("/api/rooms", json={"name": "My Sub Room", "type": "sub", "parent_id": "sub-1"})

        assert response.status_code == 400
        assert "must have a main room as a parent" in response.json()["detail"]

    def test_delete_room_logic(self):
        """Placeholder for delete tests once implemented."""
        pytest.skip("Delete room API not yet fully integrated with DB.")
