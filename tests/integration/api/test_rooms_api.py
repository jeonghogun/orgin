"""
Integration tests for Rooms API
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from app.main import app
from app.models.schemas import Room


class TestRoomsAPI:
    """Test Rooms API endpoints"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.client = TestClient(app)
        self.test_room_id = "test-room-123"
        self.test_room_name = "Test Room"
    
    @patch('app.api.routes.rooms.storage_service')
    def test_create_room_success(self, mock_storage):
        """Test successful room creation"""
        # Mock storage service
        mock_room = Room(
            room_id=self.test_room_id,
            name=self.test_room_name,
            created_at=1234567890,
            updated_at=1234567890,
            message_count=0
        )
        mock_storage.create_room = AsyncMock(return_value=mock_room)
        
        # Make request
        response = self.client.post("/api/rooms")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "room_id" in data["data"]
        assert "name" in data["data"]
        assert data["message"] == "Room created successfully"
        
        # Verify storage service was called
        mock_storage.create_room.assert_called_once()
    
    @patch('app.api.routes.rooms.storage_service')
    def test_create_room_storage_error(self, mock_storage):
        """Test room creation with storage error"""
        # Mock storage service error
        mock_storage.create_room = AsyncMock(side_effect=Exception("Storage error"))
        
        # Make request
        response = self.client.post("/api/rooms")
        
        # Verify response
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Failed to create room"
    
    @patch('app.api.routes.rooms.storage_service')
    def test_get_room_success(self, mock_storage):
        """Test successful room retrieval"""
        # Mock storage service
        mock_room = Room(
            room_id=self.test_room_id,
            name=self.test_room_name,
            created_at=1234567890,
            updated_at=1234567890,
            message_count=5
        )
        mock_storage.get_room = AsyncMock(return_value=mock_room)
        
        # Make request
        response = self.client.get(f"/api/rooms/{self.test_room_id}")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["room_id"] == self.test_room_id
        assert data["data"]["name"] == self.test_room_name
        assert data["data"]["message_count"] == 5
        
        # Verify storage service was called
        mock_storage.get_room.assert_called_once_with(self.test_room_id)
    
    @patch('app.api.routes.rooms.storage_service')
    def test_get_room_not_found(self, mock_storage):
        """Test room retrieval for non-existent room"""
        # Mock storage service returning None
        mock_storage.get_room = AsyncMock(return_value=None)
        
        # Make request
        response = self.client.get(f"/api/rooms/{self.test_room_id}")
        
        # Verify response
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Room not found"
    
    @patch('app.api.routes.rooms.storage_service')
    def test_get_room_storage_error(self, mock_storage):
        """Test room retrieval with storage error"""
        # Mock storage service error
        mock_storage.get_room = AsyncMock(side_effect=Exception("Storage error"))
        
        # Make request
        response = self.client.get(f"/api/rooms/{self.test_room_id}")
        
        # Verify response
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Failed to get room"
    
    @patch('app.api.routes.rooms.storage_service')
    def test_export_room_data_success(self, mock_storage):
        """Test successful room data export"""
        # Mock storage service
        mock_room = Room(
            room_id=self.test_room_id,
            name=self.test_room_name,
            created_at=1234567890,
            updated_at=1234567890,
            message_count=2
        )
        mock_storage.get_room = AsyncMock(return_value=mock_room)
        mock_storage.get_messages = AsyncMock(return_value=[])
        mock_storage.get_reviews = AsyncMock(return_value=[])
        
        # Make request
        response = self.client.get(f"/api/rooms/{self.test_room_id}/export")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["room_id"] == self.test_room_id
        assert data["data"]["format"] == "markdown"
        assert "export_timestamp" in data["data"]
        
        # Verify storage service calls
        mock_storage.get_room.assert_called_once_with(self.test_room_id)
        mock_storage.get_messages.assert_called_once_with(self.test_room_id)
        mock_storage.get_reviews.assert_called_once_with(self.test_room_id)
    
    @patch('app.api.routes.rooms.storage_service')
    def test_export_room_data_not_found(self, mock_storage):
        """Test room export for non-existent room"""
        # Mock storage service returning None
        mock_storage.get_room = AsyncMock(return_value=None)
        
        # Make request
        response = self.client.get(f"/api/rooms/{self.test_room_id}/export")
        
        # Verify response
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Room not found"
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = self.client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["version"] == "2.0.0"
    
    def test_debug_env(self):
        """Test debug environment endpoint"""
        response = self.client.get("/api/debug/env")
        
        assert response.status_code == 200
        data = response.json()
        assert "openai_api_key_set" in data
        assert "env_file_loaded" in data


if __name__ == "__main__":
    pytest.main([__file__])
