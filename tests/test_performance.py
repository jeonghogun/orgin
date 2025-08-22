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
            start_time: float = time.time()
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': 'Performance Test Room'}) as response:
                assert response.status == 200
                room_data: Dict[str, Any] = await response.json()
                room_id: str = room_data['room_id']
            room_creation_time: float = (time.time() - start_time) * 1000
            
            # 메시지 전송 (인증 토큰 필요)
            headers: Dict[str, str] = {'Authorization': 'Bearer dummy-id-token'}
            message_times: List[float] = []
            
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
            memory_fetch_time: float = (time.time() - start_time) * 1000
            
            # 헬스 체크
            start_time = time.time()
            async with session.get('http://127.0.0.1:8000/health') as response:
                assert response.status == 200
                await response.json()
            health_check_time: float = (time.time() - start_time) * 1000
            
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
                room_data: Dict[str, Any] = await response.json()
                room_id: str = room_data['room_id']
            
            headers: Dict[str, str] = {'Authorization': 'Bearer dummy-id-token'}
            
            # 동시에 10개의 요청 전송
            async def send_message(i: int) -> float:
                start_time: float = time.time()
                async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                      json={'role': 'user', 'content': f'Concurrent message {i}'},
                                      headers=headers) as response:
                    await response.json()
                return (time.time() - start_time) * 1000
            
            # 동시 실행
            tasks: List[asyncio.Task[float]] = [asyncio.create_task(send_message(i)) for i in range(10)]
            results: List[float] = await asyncio.gather(*tasks)
            
            print(f"\n=== Concurrent Request Test Results ===")
            print(f"Total requests: 10")
            print(f"Average response time: {statistics.mean(results):.2f}ms")
            print(f"Min response time: {min(results):.2f}ms")
            print(f"Max response time: {max(results):.2f}ms")
            print(f"Standard deviation: {statistics.stdev(results):.2f}ms")
            
            # 성능 기준 검증
            assert statistics.mean(results) < 3000, f"Average response time too slow: {statistics.mean(results)}ms"
            assert max(results) < 10000, f"Max response time too slow: {max(results)}ms"
            assert statistics.stdev(results) < 2000, f"Response time variance too high: {statistics.stdev(results)}ms"
    
    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self):
        """부하 상황에서의 메모리 사용량 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== Memory Usage Under Load Test ===")
            
            # 룸 생성
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': 'Memory Test Room'}) as response:
                assert response.status == 200
                room_data: Dict[str, Any] = await response.json()
                room_id: str = room_data['room_id']
            
            headers: Dict[str, str] = {'Authorization': 'Bearer dummy-id-token'}
            
            # 대량의 메시지 전송
            message_count: int = 50
            print(f"Sending {message_count} messages...")
            
            async def send_bulk_message(i: int) -> bool:
                try:
                    async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                          json={'role': 'user', 'content': f'Bulk message {i}' * 10},
                                          headers=headers) as response:
                        return response.status == 200
                except Exception:
                    return False
            
            # 동시 전송
            tasks: List[asyncio.Task[bool]] = [asyncio.create_task(send_bulk_message(i)) for i in range(message_count)]
            results: List[bool] = await asyncio.gather(*tasks)
            
            success_count: int = sum(results)
            print(f"Successfully sent: {success_count}/{message_count} messages")
            
            # 메모리 조회 성능 테스트
            start_time: float = time.time()
            async with session.get(f'http://127.0.0.1:8000/api/rooms/{room_id}/memory') as response:
                assert response.status == 200
                memory_data: List[Dict[str, Any]] = await response.json()
            memory_fetch_time: float = (time.time() - start_time) * 1000
            
            print(f"Memory fetch time: {memory_fetch_time:.2f}ms")
            print(f"Memory entries: {len(memory_data)}")
            
            # 성능 기준 검증
            assert success_count >= message_count * 0.9, f"Message success rate too low: {success_count}/{message_count}"
            assert memory_fetch_time < 1000, f"Memory fetch too slow: {memory_fetch_time}ms"
            assert len(memory_data) >= message_count * 0.8, f"Memory entries too few: {len(memory_data)}"
    
    @pytest.mark.asyncio
    async def test_error_recovery_performance(self):
        """에러 복구 성능 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== Error Recovery Performance Test ===")
            
            # 잘못된 요청들을 빠르게 연속 전송
            error_queries: List[str] = [
                "http://127.0.0.1:8000/api/rooms/nonexistent/messages",
                "http://127.0.0.1:8000/api/search?query=",
                "http://127.0.0.1:8000/api/nonexistent",
                "http://127.0.0.1:8000/api/rooms/invalid-id/messages"
            ]
            
            async def test_error_endpoint(url: str) -> Dict[str, Any]:
                start_time: float = time.time()
                try:
                    async with session.post(url, json={'content': 'test'}) as response:
                        return {
                            'url': url,
                            'status': response.status,
                            'time': (time.time() - start_time) * 1000,
                            'success': True
                        }
                except Exception as e:
                    return {
                        'url': url,
                        'status': None,
                        'time': (time.time() - start_time) * 1000,
                        'success': False,
                        'error': str(e)
                    }
            
            # 동시 에러 테스트
            tasks: List[asyncio.Task[Dict[str, Any]]] = [asyncio.create_task(test_error_endpoint(url)) for url in error_queries]
            results: List[Dict[str, Any]] = await asyncio.gather(*tasks)
            
            print("Error recovery test results:")
            for result in results:
                status = "✅" if result['success'] else "❌"
                print(f"  {status} {result['url']}: {result['time']:.2f}ms (status: {result.get('status', 'N/A')})")
            
            # 성능 기준 검증
            avg_error_time: float = statistics.mean([r['time'] for r in results])
            assert avg_error_time < 500, f"Error handling too slow: {avg_error_time:.2f}ms"
            
            # 에러 후 정상 요청 테스트
            print("\nTesting normal request after errors...")
            start_time = time.time()
            async with session.get('http://127.0.0.1:8000/health') as response:
                assert response.status == 200
            recovery_time: float = (time.time() - start_time) * 1000
            
            print(f"Recovery time: {recovery_time:.2f}ms")
            assert recovery_time < 200, f"Recovery too slow: {recovery_time:.2f}ms"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



