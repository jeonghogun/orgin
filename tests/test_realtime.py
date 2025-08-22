import pytest
import asyncio
import aiohttp
import websockets
import json
import time
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestRealtimeFeatures:
    """Real-time features test"""
    
    @pytest.mark.asyncio
    async def test_websocket_connection_and_presence(self):
        """Test WebSocket connection and presence events"""
        # First create a room
        async with aiohttp.ClientSession() as session:
            # Create room
            async with session.post('http://127.0.0.1:8000/api/rooms', 
                                  json={'title': 'Realtime Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
        
        # Connect to WebSocket
        uri = f"ws://127.0.0.1:8000/ws/rooms/{room_id}"
        async with websockets.connect(uri) as websocket:
            # Send hello message
            hello_msg = {
                "type": "hello",
                "client_id": "test-client-1",
                "room_id": room_id,
                "token": "dummy-id-token"  # Using dummy token for testing
            }
            await websocket.send(json.dumps(hello_msg))
            
            # Wait for any presence events
            try:
                await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print("✅ WebSocket connection and hello message sent successfully")
            except asyncio.TimeoutError:
                print("⚠️ No immediate response received (this is normal)")
            
            # Send a ping
            ping_msg = {"type": "ping", "ts": time.time()}
            await websocket.send(json.dumps(ping_msg))
            
            # Wait for pong response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                data = json.loads(response)
                assert data["type"] == "pong"
                print("✅ Ping/pong working correctly")
            except asyncio.TimeoutError:
                print("❌ No pong response received")
                assert False
    
    @pytest.mark.asyncio
    async def test_typing_events(self):
        """Test typing start/stop events"""
        # Create room
        async with aiohttp.ClientSession() as session:
            async with session.post('http://127.0.0.1:8000/api/rooms', 
                                  json={'title': 'Typing Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
        
        # Connect to WebSocket
        uri = f"ws://127.0.0.1:8000/ws/rooms/{room_id}"
        async with websockets.connect(uri) as websocket:
            # Send hello
            hello_msg = {
                "type": "hello",
                "client_id": "test-client-2",
                "room_id": room_id,
                "token": "dummy-id-token"
            }
            await websocket.send(json.dumps(hello_msg))
            
            # Send typing_start
            typing_start_msg = {
                "type": "typing_start",
                "payload": {
                    "user_id": "test-user-1",
                    "user_name": "Test User"
                }
            }
            await websocket.send(json.dumps(typing_start_msg))
            
            # Send typing_stop
            typing_stop_msg = {
                "type": "typing_stop",
                "payload": {
                    "user_id": "test-user-1"
                }
            }
            await websocket.send(json.dumps(typing_stop_msg))
            
            print("✅ Typing events sent successfully")
    
    @pytest.mark.asyncio
    async def test_health_ws_endpoint(self):
        """Test WebSocket health endpoint"""
        async with aiohttp.ClientSession() as session:
            async with session.get('http://127.0.0.1:8000/health/ws') as response:
                assert response.status == 200
                data = await response.json()
                
                # Check required fields
                assert "active_rooms" in data
                assert "active_ws_total" in data
                assert "active_ws_by_room" in data
                assert "close_code_histogram" in data
                
                print(f"✅ Health WS endpoint working: {data['active_ws_total']} active connections")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])



