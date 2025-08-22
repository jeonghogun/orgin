import pytest
import asyncio
import aiohttp
import websockets
import json
import time
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestPresenceDebug:
    """Debug presence issues"""
    
    @pytest.mark.asyncio
    async def test_presence_with_auth_token(self):
        """Test presence with proper auth token"""
        # Create a room
        async with aiohttp.ClientSession() as session:
            async with session.post('http://127.0.0.1:8000/api/rooms', 
                                  json={'title': 'Presence Debug Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
                print(f"Created room: {room_id}")
        
        # Connect WebSocket with dummy token
        uri = f"ws://127.0.0.1:8000/ws/rooms/{room_id}"
        async with websockets.connect(uri) as websocket:
            # Send hello with dummy token
            hello_msg = {
                "type": "hello",
                "client_id": "test-client-debug",
                "room_id": room_id,
                "token": "dummy-id-token"
            }
            print(f"Sending HELLO: {hello_msg}")
            await websocket.send(json.dumps(hello_msg))
            
            # Wait for presence events
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                data = json.loads(response)
                print(f"Received: {data}")
                if data.get("type") == "presence_join":
                    print("✅ Presence join event received")
                    print(f"  User ID: {data.get('user_id')}")
                    print(f"  Client ID: {data.get('client_id')}")
                    print(f"  User Name: {data.get('user_name')}")
                else:
                    print(f"⚠️ Unexpected event type: {data.get('type')}")
            except asyncio.TimeoutError:
                print("⚠️ No presence event received within 3 seconds")
            
            # Check health endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get('http://127.0.0.1:8000/health/ws') as response:
                    data = await response.json()
                    print(f"Health WS: {data}")
                    assert room_id in data['active_ws_by_room']
                    print(f"✅ Active connections for room: {data['active_ws_by_room'][room_id]}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
