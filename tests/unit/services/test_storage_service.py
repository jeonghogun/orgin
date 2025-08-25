"""
Unit tests for Storage Service
"""
import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from typing import Dict, Any

from app.services.storage_service import StorageService
from app.models.schemas import Room, Message, ReviewMeta


class TestStorageService:
    """Test Storage Service"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Create temporary directory for tests
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        with patch('app.services.storage_service.settings') as mock_settings:
            mock_settings.DATA_DIR = str(self.data_dir)
            mock_settings.FIREBASE_SERVICE_ACCOUNT_PATH = None
            self.service = StorageService()
    
    def teardown_method(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_initialization(self):
        """Test service initialization"""
        assert self.service.data_dir == self.data_dir
        assert self.service.firebase_service is None
    
    @patch('app.services.storage_service.FirebaseService')
    def test_initialization_with_firebase(self, mock_firebase_class):
        """Test initialization with Firebase enabled"""
        mock_firebase = MagicMock()
        mock_firebase_class.return_value = mock_firebase
        
        with patch('app.services.storage_service.settings') as mock_settings:
            mock_settings.DATA_DIR = str(self.data_dir)
            mock_settings.FIREBASE_SERVICE_ACCOUNT_PATH = "test-path"
            
            service = StorageService()
            
            assert service.firebase_service == mock_firebase
            mock_firebase_class.assert_called_once()
    
    def test_memory_operations(self):
        """Test memory operations"""
        room_id = "test-room"
        key = "test-key"
        value = "test-value"
        
        # Test memory set
        self.service.memory_set(room_id, key, value)
        
        # Test memory get
        retrieved_value = self.service.memory_get(room_id, key)
        assert retrieved_value == value
        
        # Test memory clear
        self.service.memory_clear(room_id)
        cleared_value = self.service.memory_get(room_id, key)
        assert cleared_value is None
    
    def test_get_room_path(self):
        """Test room path generation"""
        room_id = "test-room-123"
        expected_path = self.data_dir / "rooms" / room_id
        
        result = self.service._get_room_path(room_id)
        assert result == expected_path
    
    def test_get_review_path(self):
        """Test review path generation"""
        review_id = "test-review-456"
        expected_path = self.data_dir / "reviews" / review_id
        
        result = self.service._get_review_path(review_id)
        assert result == expected_path
    
    def test_safe_write_json(self):
        """Test safe JSON writing"""
        test_data = {"key": "value", "number": 123}
        file_path = self.data_dir / "test.json"
        
        self.service._safe_write_json(file_path, test_data)
        
        # Verify file was created
        assert file_path.exists()
        
        # Verify content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        assert content == test_data
    
    def test_safe_read_json_existing(self):
        """Test safe JSON reading from existing file"""
        test_data = {"key": "value", "number": 123}
        file_path = self.data_dir / "test.json"
        
        # Write test data
        self.service._safe_write_json(file_path, test_data)
        
        # Read data
        result = self.service._safe_read_json(file_path)
        assert result == test_data
    
    def test_safe_read_json_nonexistent(self):
        """Test safe JSON reading from non-existent file"""
        file_path = self.data_dir / "nonexistent.json"
        
        result = self.service._safe_read_json(file_path)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_create_room_success(self):
        """Test successful room creation"""
        room_id = "test-room"
        name = "Test Room"
        
        result = await self.service.create_room(room_id, name)
        
        assert isinstance(result, Room)
        assert result.room_id == room_id
        assert result.name == name
        assert result.message_count == 0
        
        # Verify file was created
        room_file = self.data_dir / "rooms" / f"{room_id}.json"
        assert room_file.exists()
    
    @pytest.mark.asyncio
    async def test_create_room_with_firebase(self):
        """Test room creation with Firebase enabled"""
        mock_firebase = MagicMock()
        mock_firebase.create_room = AsyncMock()
        self.service.firebase_service = mock_firebase
        
        room_id = "test-room"
        name = "Test Room"
        
        await self.service.create_room(room_id, name)
        
        # Verify Firebase was called
        mock_firebase.create_room.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_room_existing(self):
        """Test getting existing room"""
        room_id = "test-room"
        name = "Test Room"
        
        # Create room first
        created_room = await self.service.create_room(room_id, name)
        
        # Get room
        retrieved_room = await self.service.get_room(room_id)
        
        assert retrieved_room is not None
        assert retrieved_room.room_id == room_id
        assert retrieved_room.name == name
    
    @pytest.mark.asyncio
    async def test_get_room_nonexistent(self):
        """Test getting non-existent room"""
        room_id = "nonexistent-room"
        
        result = await self.service.get_room(room_id)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_save_message_success(self):
        """Test successful message saving"""
        message = Message(
            message_id="msg-123",
            room_id="room-123",
            user_id="user-123",
            content="Hello, world!",
            timestamp=1234567890,
            role="user"
        )
        
        await self.service.save_message(message)
        
        # Verify file was created
        room_dir = self.data_dir / "rooms" / "room-123"
        messages_file = room_dir / "messages.json"
        assert messages_file.exists()
        
        # Verify content
        with open(messages_file, 'r', encoding='utf-8') as f:
            messages = json.load(f)
        
        assert len(messages) == 1
        assert messages[0]["message_id"] == "msg-123"
        assert messages[0]["content"] == "Hello, world!"
    
    @pytest.mark.asyncio
    async def test_get_messages_existing(self):
        """Test getting messages from existing room"""
        room_id = "room-123"
        
        # Create messages
        message1 = Message(
            message_id="msg-1",
            room_id=room_id,
            user_id="user-123",
            content="Message 1",
            timestamp=1234567890,
            role="user"
        )
        
        message2 = Message(
            message_id="msg-2",
            room_id=room_id,
            user_id="ai",
            content="Message 2",
            timestamp=1234567891,
            role="ai"
        )
        
        await self.service.save_message(message1)
        await self.service.save_message(message2)
        
        # Get messages
        messages = await self.service.get_messages(room_id)
        
        assert len(messages) == 2
        assert messages[0].message_id == "msg-1"
        assert messages[1].message_id == "msg-2"
    
    @pytest.mark.asyncio
    async def test_get_messages_nonexistent(self):
        """Test getting messages from non-existent room"""
        room_id = "nonexistent-room"
        
        messages = await self.service.get_messages(room_id)
        assert messages == []
    
    @pytest.mark.asyncio
    async def test_save_review_meta_success(self):
        """Test successful review metadata saving"""
        review_meta = ReviewMeta(
            review_id="review-123",
            room_id="room-123",
            topic="Test Topic",
            status="in_progress",
            total_rounds=3,
            current_round=0,
            created_at=1234567890,
            failed_panels=[]
        )
        
        await self.service.save_review_meta(review_meta)
        
        # Verify file was created
        review_file = self.data_dir / "reviews" / "review-123.json"
        assert review_file.exists()
        
        # Verify content
        with open(review_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["review_id"] == "review-123"
        assert data["topic"] == "Test Topic"
        assert data["status"] == "in_progress"


if __name__ == "__main__":
    pytest.main([__file__])
