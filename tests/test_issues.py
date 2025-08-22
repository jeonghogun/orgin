import pytest
import asyncio
import aiohttp
import websockets
import json
import time
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestIssues:
    """Test for reported issues"""
    
    @pytest.mark.asyncio
    async def test_review_creation_room_id_mismatch(self):
        """Test that review creation uses correct room_id"""
        # Create a room
        async with aiohttp.ClientSession() as session:
            async with session.post('http://127.0.0.1:8000/api/rooms', 
                                  json={'title': 'Review Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
                print(f"Created room: {room_id}")
            
            # Try to create review with correct room_id
            review_request = {
                "topic": "Test Topic",
                "rounds": [
                    {
                        "round_number": 1,
                        "mode": "divergent",
                        "instruction": "Test instruction",
                        "panel_personas": [
                            {"name": "Test Panelist", "provider": "openai"}
                        ]
                    }
                ]
            }
            
            headers = {'Authorization': 'Bearer dummy-id-token'}
            async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/reviews',
                                  json=review_request,
                                  headers=headers) as response:
                print(f"Review creation response: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"Review created: {data['review_id']}")
                    assert data['room_id'] == room_id
                else:
                    error_data = await response.json()
                    print(f"Error: {error_data}")
                    assert False, f"Review creation failed: {error_data}"
    
    @pytest.mark.asyncio
    async def test_presence_count_multiple_tabs(self):
        """Test presence count with multiple connections"""
        # Create a room
        async with aiohttp.ClientSession() as session:
            async with session.post('http://127.0.0.1:8000/api/rooms', 
                                  json={'title': 'Presence Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
        
        # Connect first WebSocket
        uri = f"ws://127.0.0.1:8000/ws/rooms/{room_id}"
        async with websockets.connect(uri) as ws1:
            hello1 = {
                "type": "hello",
                "client_id": "test-client-1",
                "room_id": room_id,
                "token": "dummy-id-token"
            }
            await ws1.send(json.dumps(hello1))
            
            # Wait a bit for presence to register
            await asyncio.sleep(1)
            
            # Check health
            async with aiohttp.ClientSession() as session:
                async with session.get('http://127.0.0.1:8000/health/ws') as response:
                    data = await response.json()
                    print(f"After first connection: {data['active_ws_by_room']}")
                    assert room_id in data['active_ws_by_room']
                    assert data['active_ws_by_room'][room_id] >= 1
            
            # Connect second WebSocket (simulating second tab)
            async with websockets.connect(uri) as ws2:
                hello2 = {
                    "type": "hello",
                    "client_id": "test-client-2",
                    "room_id": room_id,
                    "token": "dummy-id-token"
                }
                await ws2.send(json.dumps(hello2))
                
                # Wait a bit for presence to register
                await asyncio.sleep(1)
                
                # Check health again
                async with aiohttp.ClientSession() as session:
                    async with session.get('http://127.0.0.1:8000/health/ws') as response:
                        data = await response.json()
                        print(f"After second connection: {data['active_ws_by_room']}")
                        assert room_id in data['active_ws_by_room']
                        assert data['active_ws_by_room'][room_id] >= 2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])



