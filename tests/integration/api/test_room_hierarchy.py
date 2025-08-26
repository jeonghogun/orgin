import pytest
from fastapi.testclient import TestClient
from app.models.schemas import Room
from tests.conftest import USER_ID

class TestRoomHierarchy:
    """Tests for room creation and hierarchy rules using the live test database."""

    def test_create_main_room_success(self, authenticated_client: TestClient):
        """Test creating a main room successfully."""
        response = authenticated_client.post("/api/rooms", json={"name": "My Main Room", "type": "main"})
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "main"
        assert data["owner_id"] == USER_ID

    def test_create_main_room_fails_if_already_exists(self, authenticated_client: TestClient):
        """A user cannot create more than one main room."""
        # First, create one main room, which should succeed.
        response1 = authenticated_client.post("/api/rooms", json={"name": "First Main", "type": "main"})
        assert response1.status_code == 200

        # Now, try to create another, which should fail.
        response2 = authenticated_client.post("/api/rooms", json={"name": "Second Main", "type": "main"})
        assert response2.status_code == 400
        assert "Main room already exists" in response2.json()["detail"]

    def test_create_sub_room_success(self, authenticated_client: TestClient):
        """Test creating a sub room successfully."""
        # Create a main room to be the parent
        main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for Sub", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        # Create the sub-room
        response = authenticated_client.post("/api/rooms", json={"name": "My Sub Room", "type": "sub", "parent_id": main_room_id})
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "sub"
        assert data["parent_id"] == main_room_id

    def test_create_sub_room_fails_with_invalid_parent_type(self, authenticated_client: TestClient):
        """Test creating a sub room fails if the parent is not a main room."""
        # Create a main room, and a sub-room within it.
        main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main Room", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        sub_room_res = authenticated_client.post("/api/rooms", json={"name": "Sub Room 1", "type": "sub", "parent_id": main_room_id})
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        # Try to create a sub-room with another sub-room as its parent.
        response = authenticated_client.post("/api/rooms", json={"name": "Sub Room 2", "type": "sub", "parent_id": sub_room_id})
        assert response.status_code == 400
        assert "must have a main room as a parent" in response.json()["detail"]

    def test_delete_room_logic(self, authenticated_client: TestClient):
        """Test deleting a sub-room."""
        # Create a main room and a sub-room
        main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for Delete", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        sub_room_res = authenticated_client.post("/api/rooms", json={"name": "Sub to Delete", "type": "sub", "parent_id": main_room_id})
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        # Delete the sub-room
        delete_res = authenticated_client.delete(f"/api/rooms/{sub_room_id}")
        assert delete_res.status_code == 204

        # Verify it's gone
        get_res = authenticated_client.get(f"/api/rooms/{sub_room_id}")
        assert get_res.status_code == 404
