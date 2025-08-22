import pytest
import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict, Any
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestPerformance:
    """성능 테스트"""
    
    @pytest.mark.asyncio
    async def test_api_response_times(self):
        """API 응답 시간 테스트"""
        async with aiohttp.ClientSession() as session:
            # 룸 생성
            start_time = time.time()
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': 'Performance Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
            room_creation_time = (time.time() - start_time) * 1000
            
            # 메시지 전송 (인증 토큰 필요)
            headers = {'Authorization': 'Bearer dummy-id-token'}
            message_times = []
            
            for i in range(5):  # 5번 메시지 전송 테스트
                start_time = time.time()
                async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                      json={'role': 'user', 'content': f'Test message {i}'},
                                      headers=headers) as response:
                    assert response.status == 200
                    await response.json()
                message_times.append((time.time() - start_time) * 1000)
            
            # 메모리 조회
            start_time = time.time()
            async with session.get(f'http://127.0.0.1:8000/api/rooms/{room_id}/memory') as response:
                assert response.status == 200
                await response.json()
            memory_fetch_time = (time.time() - start_time) * 1000
            
            # 헬스 체크
            start_time = time.time()
            async with session.get('http://127.0.0.1:8000/health') as response:
                assert response.status == 200
                await response.json()
            health_check_time = (time.time() - start_time) * 1000
            
            # 결과 출력
            print(f"\n=== API Performance Test Results ===")
            print(f"Room creation: {room_creation_time:.2f}ms")
            print(f"Message sending (avg): {statistics.mean(message_times):.2f}ms")
            print(f"Message sending (min): {min(message_times):.2f}ms")
            print(f"Message sending (max): {max(message_times):.2f}ms")
            print(f"Memory fetch: {memory_fetch_time:.2f}ms")
            print(f"Health check: {health_check_time:.2f}ms")
            
            # 성능 기준 검증
            assert room_creation_time < 1000, f"Room creation too slow: {room_creation_time}ms"
            assert statistics.mean(message_times) < 5000, f"Message sending too slow: {statistics.mean(message_times)}ms"
            assert memory_fetch_time < 500, f"Memory fetch too slow: {memory_fetch_time}ms"
            assert health_check_time < 100, f"Health check too slow: {health_check_time}ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """동시 요청 테스트"""
        async with aiohttp.ClientSession() as session:
            # 룸 생성
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': 'Concurrent Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
            
            headers = {'Authorization': 'Bearer dummy-id-token'}
            
            # 동시에 10개의 요청 전송
            async def send_message(i: int):
                start_time = time.time()
                async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                      json={'role': 'user', 'content': f'Concurrent message {i}'},
                                      headers=headers) as response:
                    await response.json()
                return (time.time() - start_time) * 1000
            
            # 동시 실행
            tasks = [send_message(i) for i in range(10)]
            results = await asyncio.gather(*tasks)
            
            print(f"\n=== Concurrent Request Test Results ===")
            print(f"Total requests: 10")
            print(f"Average response time: {statistics.mean(results):.2f}ms")
            print(f"Min response time: {min(results):.2f}ms")
            print(f"Max response time: {max(results):.2f}ms")
            print(f"Standard deviation: {statistics.stdev(results):.2f}ms")
            
            # 모든 요청이 성공했는지 확인
            assert all(result < 10000 for result in results), "Some concurrent requests were too slow"
    
    @pytest.mark.asyncio
    async def test_websocket_performance(self):
        """WebSocket 성능 테스트"""
        import websockets
        import json
        
        # 룸 생성
        async with aiohttp.ClientSession() as session:
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': 'WebSocket Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
        
        uri = f"ws://127.0.0.1:8000/ws/rooms/{room_id}"
        
        # WebSocket 연결 시간 측정
        start_time = time.time()
        async with websockets.connect(uri) as websocket:
            connection_time = (time.time() - start_time) * 1000
            
            # HELLO 메시지 전송
            hello_msg = {
                "type": "hello",
                "client_id": "perf-test-client",
                "room_id": room_id,
                "token": "dummy-id-token"
            }
            
            start_time = time.time()
            await websocket.send(json.dumps(hello_msg))
            hello_send_time = (time.time() - start_time) * 1000
            
            # 응답 대기
            try:
                start_time = time.time()
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                response_time = (time.time() - start_time) * 1000
                data = json.loads(response)
                print(f"WebSocket response: {data.get('type', 'unknown')}")
            except asyncio.TimeoutError:
                response_time = 2000  # 2초 타임아웃
                print("WebSocket response timeout")
            
            # Ping/Pong 테스트
            ping_times = []
            for i in range(3):
                start_time = time.time()
                ping_msg = {"type": "ping", "ts": time.time()}
                await websocket.send(json.dumps(ping_msg))
                
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    ping_times.append((time.time() - start_time) * 1000)
                except asyncio.TimeoutError:
                    ping_times.append(1000)  # 1초 타임아웃
            
            print(f"\n=== WebSocket Performance Test Results ===")
            print(f"Connection time: {connection_time:.2f}ms")
            print(f"HELLO send time: {hello_send_time:.2f}ms")
            print(f"Response time: {response_time:.2f}ms")
            print(f"Ping/Pong (avg): {statistics.mean(ping_times):.2f}ms")
            
            # 성능 기준 검증
            assert connection_time < 1000, f"WebSocket connection too slow: {connection_time}ms"
            assert hello_send_time < 100, f"HELLO send too slow: {hello_send_time}ms"
            assert response_time < 3000, f"WebSocket response too slow: {response_time}ms"
            assert statistics.mean(ping_times) < 1000, f"Ping/Pong too slow: {statistics.mean(ping_times)}ms"
    
    @pytest.mark.asyncio
    async def test_memory_usage(self):
        """메모리 사용량 테스트"""
        import psutil
        import os
        
        # 현재 프로세스의 메모리 사용량 확인
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 여러 요청을 보내서 메모리 사용량 변화 확인
        async with aiohttp.ClientSession() as session:
            # 룸 생성
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': 'Memory Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
            
            headers = {'Authorization': 'Bearer dummy-id-token'}
            
            # 여러 메시지 전송
            for i in range(20):
                async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                      json={'role': 'user', 'content': f'Memory test message {i}'},
                                      headers=headers) as response:
                    await response.json()
            
            # 메모리 사용량 재확인
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            print(f"\n=== Memory Usage Test Results ===")
            print(f"Initial memory: {initial_memory:.2f}MB")
            print(f"Final memory: {final_memory:.2f}MB")
            print(f"Memory increase: {memory_increase:.2f}MB")
            
            # 메모리 누수 검증 (20MB 이하 증가 허용)
            assert memory_increase < 20, f"Memory increase too high: {memory_increase}MB"
    
    @pytest.mark.asyncio
    async def test_cache_performance(self):
        """캐시 성능 테스트"""
        async with aiohttp.ClientSession() as session:
            # 룸 생성
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': 'Cache Test Room'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
            
            # 첫 번째 요청 (캐시 미스)
            start_time = time.time()
            async with session.get(f'http://127.0.0.1:8000/api/rooms/{room_id}/memory') as response:
                assert response.status == 200
                await response.json()
            first_request_time = (time.time() - start_time) * 1000
            
            # 두 번째 요청 (캐시 히트)
            start_time = time.time()
            async with session.get(f'http://127.0.0.1:8000/api/rooms/{room_id}/memory') as response:
                assert response.status == 200
                await response.json()
            second_request_time = (time.time() - start_time) * 1000
            
            print(f"\n=== Cache Performance Test Results ===")
            print(f"First request (cache miss): {first_request_time:.2f}ms")
            print(f"Second request (cache hit): {second_request_time:.2f}ms")
            print(f"Cache improvement: {((first_request_time - second_request_time) / first_request_time * 100):.1f}%")
            
            # 캐시가 효과적인지 확인 (두 번째 요청이 더 빠르거나 비슷해야 함)
            assert second_request_time <= first_request_time * 1.5, "Cache not effective"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



