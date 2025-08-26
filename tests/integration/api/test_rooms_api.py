import pytest
from fastapi.testclient import TestClient

from app.models.schemas import Room
from tests.conftest import USER_ID

class TestRoomsAPI:
    """Test room API endpoints with a live database."""

    def test_get_room_success(self, authenticated_client: TestClient):
        """Test successful room retrieval."""
        # 1. Create a room
        create_res = authenticated_client.post("/api/rooms", json={"name": "Get Me Room", "type": "main"})
        assert create_res.status_code == 200
        room_id = create_res.json()["room_id"]

        # 2. Get the room
        response = authenticated_client.get(f"/api/rooms/{room_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == room_id
        assert data["name"] == "Get Me Room"

    def test_get_room_not_found(self, authenticated_client: TestClient):
        """Test room retrieval for non-existent room."""
        response = authenticated_client.get("/api/rooms/non-existent-room-id")
        assert response.status_code == 404

    def test_get_room_storage_error(self, authenticated_client: TestClient, monkeypatch):
        """Test room retrieval with a simulated storage error."""
        # We can simulate a DB error by patching the underlying service method
        async def mock_get_room_error(*args, **kwargs):
            raise Exception("Simulated DB is down")

        monkeypatch.setattr(
            "app.api.routes.rooms.storage_service.get_room",
            mock_get_room_error
        )

        response = authenticated_client.get("/api/rooms/any-id")
        assert response.status_code == 500
        assert "Failed to retrieve room" in response.json()["detail"]

    def test_export_room_data_success(self, authenticated_client: TestClient):
        """Test successful room data export."""
        # 1. Create a room and add a message
        create_res = authenticated_client.post("/api/rooms", json={"name": "Export Room", "type": "main"})
        assert create_res.status_code == 200
        room_id = create_res.json()["room_id"]

        msg_res = authenticated_client.post(f"/api/rooms/{room_id}/messages", json={"content": "Export this message"})
        assert msg_res.status_code == 200

        # 2. Export the data
        response = authenticated_client.get(f"/api/rooms/{room_id}/export")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["room_id"] == room_id
        assert len(data["messages"]) > 0
        assert data["messages"][0]["content"] == "Export this message"

    def test_health_check(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_debug_env(self, client: TestClient):
        """Test debug environment endpoint."""
        response = client.get("/api/debug/env")
        assert response.status_code == 200
        assert "openai_api_key_set" in response.json()
