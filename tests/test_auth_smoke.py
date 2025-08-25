import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.main import app
from app.config.settings import settings
from app.api.dependencies import require_auth

@pytest.fixture
def client():
    """A TestClient instance for FastAPI app, ensuring clean dependency overrides."""
    original_overrides = app.dependency_overrides.copy()
    yield TestClient(app)
    app.dependency_overrides = original_overrides


class TestAuthSmoke:
    """Authentication smoke tests."""

    def test_health_endpoint_accessible(self, client):
        """Test that health endpoint is accessible without authentication."""
        response = client.get("/health")
        assert response.status_code == 200

    @patch("app.services.storage_service.StorageService", new_callable=AsyncMock)
    @patch("app.services.llm_service.LLMService", new_callable=AsyncMock)
    @patch("app.services.rag_service.RAGService", new_callable=AsyncMock)
    def test_message_send_with_dummy_token(self, mock_rag, mock_llm, mock_storage, client, monkeypatch):
        """Test message sending with dummy token when AUTH_OPTIONAL=True"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", True)

        # Mock the storage service to return a valid room
        mock_storage.get_room.return_value = {"id": "smoke-room", "name": "Smoke Test Room"}
        mock_storage.get_messages.return_value = []
        mock_llm.get_provider.return_value.invoke.return_value = "AI response"

        # Override the auth dependency to return an anonymous user
        app.dependency_overrides[require_auth] = lambda: {"user_id": "anonymous"}

        room_id = "smoke-test-room"
        headers = {"Authorization": "Bearer dummy-id-token"}
        response = client.post(
            f"/api/rooms/{room_id}/messages",
            json={"content": "Test message"},
            headers=headers,
        )
        assert response.status_code == 200
        assert "ai_response" in response.json()["data"]

    def test_message_send_without_token_fails(self, client, monkeypatch):
        """Test that message sending without token fails when AUTH_OPTIONAL=False"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)
        
        room_id = "smoke-test-room"

        # Send message without token
        response = client.post(
            f"/api/rooms/{room_id}/messages",
            json={"content": "Test message"},
        )
        assert response.status_code == 401  # Unauthorized
