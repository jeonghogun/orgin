from fastapi.testclient import TestClient

class TestRoomsAPI:
    """Test room API endpoints with a live database."""

    def test_get_room_success(self, authenticated_client: TestClient):
        """Test successful room retrieval."""
        # Use the existing room created by authenticated_client fixture
        response = authenticated_client.get("/api/rooms/room_main_1")
        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == "room_main_1"
        assert data["name"] == "Main Room"

    def test_get_room_not_found(self, authenticated_client: TestClient):
        """Test room retrieval for non-existent room."""
        response = authenticated_client.get("/api/rooms/non-existent-room-id")
        assert response.status_code == 404

    def test_get_room_storage_error(self, authenticated_client: TestClient, monkeypatch):
        """Test room retrieval with a simulated storage error."""
        # We can simulate a DB error by patching the underlying service method
        def mock_get_room_error(*args, **kwargs):
            raise Exception("Simulated DB is down")

        monkeypatch.setattr(
            "app.api.routes.rooms.storage_service.get_room",
            mock_get_room_error
        )

        response = authenticated_client.get("/api/rooms/any-id")
        assert response.status_code == 500
        assert "Failed to retrieve room" in response.json()["error"]["message"]

    def test_export_room_data_success(self, authenticated_client: TestClient):
        """Test successful room data export."""
        # Use the existing room created by authenticated_client fixture
        room_id = "room_main_1"

        # 1. Add a message to the existing room
        msg_res = authenticated_client.post(f"/api/rooms/{room_id}/messages", json={"content": "Export this message"})
        assert msg_res.status_code == 200

        # 2. Export the data
        response = authenticated_client.get(f"/api/rooms/{room_id}/export")
        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == room_id
        assert len(data["messages"]) > 0
        assert data["messages"][0]["content"] == "Export this message"

    def test_health_check(self, authenticated_client: TestClient):
        """Test health check endpoint."""
        response = authenticated_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_debug_env_permission_denied_for_user(self, authenticated_client: TestClient):
        """Test that a regular user cannot access the debug endpoint."""
        response = authenticated_client.get("/api/debug/env")
        assert response.status_code == 403

    def test_debug_env_success_for_admin(self, authenticated_client: TestClient, test_user_id: str, isolated_test_env, monkeypatch):
        """Test that an admin user can access the debug endpoint."""
        # Override the debug endpoint dependency directly
        from app.main import app
        from app.api.dependencies import require_role
        
        # Create a mock role checker that always allows access
        async def mock_admin_role_checker(user_info, memory_service):
            return user_info
        
        # Override the require_role function itself to return our mock
        def mock_require_role(role):
            return mock_admin_role_checker
        
        # Patch the require_role function
        monkeypatch.setattr("app.api.dependencies.require_role", mock_require_role)

        # Access the endpoint
        response = authenticated_client.get("/api/debug/env")

        # Assert success
        assert response.status_code == 200
        assert "openai_api_key_set" in response.json()
