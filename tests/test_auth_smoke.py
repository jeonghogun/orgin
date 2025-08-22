import pytest
import asyncio
import aiohttp
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestAuthSmoke:
    """Authentication smoke tests"""
    
    @pytest.mark.asyncio
    async def test_health_endpoint_accessible(self):
        """Test that health endpoint is accessible without authentication"""
        async with aiohttp.ClientSession() as session:
            async with session.get('http://127.0.0.1:8000/health') as response:
                assert response.status == 200
                data = await response.json()
                assert data['status'] == 'healthy'
    
    @pytest.mark.asyncio
    async def test_message_send_with_dummy_token(self):
        """Test message sending with dummy token when AUTH_OPTIONAL=True"""
        # First create a room
        async with aiohttp.ClientSession() as session:
            # Create room
            async with session.post('http://127.0.0.1:8000/api/rooms', 
                                  json={'title': 'Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
            
            # Send message with dummy token
            headers = {'Authorization': 'Bearer dummy-id-token'}
            async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                  json={'role': 'user', 'content': 'Test message'},
                                  headers=headers) as response:
                assert response.status == 200
                data = await response.json()
                assert 'message_id' in data
    
    @pytest.mark.asyncio
    async def test_message_send_without_token_fails(self):
        """Test that message sending without token fails when AUTH_OPTIONAL=False"""
        # Temporarily change AUTH_OPTIONAL to False
        from app.config.settings import settings
        original_value = settings.AUTH_OPTIONAL
        settings.AUTH_OPTIONAL = False
        
        try:
            async with aiohttp.ClientSession() as session:
                # Create room
                async with session.post('http://127.0.0.1:8000/api/rooms', 
                                      json={'title': 'Test Room 2'}) as response:
                    assert response.status == 200
                    room_data = await response.json()
                    room_id = room_data['room_id']
                
                # Send message without token
                async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                      json={'role': 'user', 'content': 'Test message'}) as response:
                    assert response.status == 403  # Forbidden (Not authenticated)
        finally:
            settings.AUTH_OPTIONAL = original_value

if __name__ == "__main__":
    pytest.main([__file__])
