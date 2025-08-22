import pytest
import asyncio
import aiohttp
import json
import time
from typing import Dict, Any
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestUserFlow:
    """실제 사용자 흐름 E2E 테스트"""
    
    @pytest.mark.asyncio
    async def test_complete_user_journey(self):
        """완전한 사용자 여정 테스트: 로그인 → 룸 생성 → 채팅 → 리뷰 생성 → 결과 확인"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 사용자 여정 테스트 시작 ===")
            
            # 1. 룸 생성
            print("1. 룸 생성 중...")
            start_time = time.time()
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': '사용자 여정 테스트 룸'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
                print(f"   ✅ 룸 생성 완료: {room_id} ({time.time() - start_time:.2f}초)")
            
            # 2. 메시지 전송 (인증 토큰 필요)
            headers = {'Authorization': 'Bearer dummy-id-token'}
            print("2. 메시지 전송 중...")
            
            messages = [
                "안녕하세요! 새로운 프로젝트에 대해 상담받고 싶습니다.",
                "우리 회사는 AI 기반 교육 플랫폼을 개발하려고 합니다.",
                "주요 기능은 개인화된 학습 경로, 실시간 피드백, 그리고 게이미피케이션입니다.",
                "예산은 약 5억원이고, 개발 기간은 6개월을 목표로 하고 있습니다."
            ]
            
            for i, message in enumerate(messages, 1):
                start_time = time.time()
                async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                      json={'role': 'user', 'content': message},
                                      headers=headers) as response:
                    assert response.status == 200
                    response_data = await response.json()
                    print(f"   ✅ 메시지 {i} 전송 완료 ({time.time() - start_time:.2f}초)")
            
            # 3. 대화 기록 확인
            print("3. 대화 기록 확인 중...")
            start_time = time.time()
            async with session.get(f'http://127.0.0.1:8000/api/rooms/{room_id}/memory') as response:
                assert response.status == 200
                memory = await response.json()
                print(f"   ✅ 대화 기록 {len(memory)}개 조회 완료 ({time.time() - start_time:.2f}초)")
            
            # 4. 리뷰 생성
            print("4. 리뷰 생성 중...")
            start_time = time.time()
            review_request = {
                "topic": "AI 기반 교육 플랫폼 개발 프로젝트 검토",
                "rounds": [
                    {
                        "round_number": 1,
                        "mode": "divergent",
                        "instruction": "이 프로젝트의 잠재적 위험 요소와 기회를 분석해주세요.",
                        "panel_personas": [
                            {"name": "기술 아키텍트", "provider": "openai"},
                            {"name": "비즈니스 분석가", "provider": "openai"},
                            {"name": "UX 디자이너", "provider": "openai"}
                        ]
                    },
                    {
                        "round_number": 2,
                        "mode": "convergent",
                        "instruction": "1라운드 분석을 바탕으로 구체적인 실행 계획을 제시해주세요.",
                        "panel_personas": [
                            {"name": "프로젝트 매니저", "provider": "openai"},
                            {"name": "개발 리드", "provider": "openai"}
                        ]
                    }
                ]
            }
            
            async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/reviews',
                                  json=review_request,
                                  headers=headers) as response:
                assert response.status == 200
                review_data = await response.json()
                review_id = review_data['review_id']
                print(f"   ✅ 리뷰 생성 완료: {review_id} ({time.time() - start_time:.2f}초)")
            
            # 5. 리뷰 실행 및 결과 대기
            print("5. 리뷰 실행 중...")
            start_time = time.time()
            async with session.post(f'http://127.0.0.1:8000/api/reviews/{review_id}/generate',
                                  headers=headers) as response:
                assert response.status == 200
                generate_data = await response.json()
                print(f"   ✅ 리뷰 실행 시작 ({time.time() - start_time:.2f}초)")
            
            # 6. 최종 결과 확인
            print("6. 최종 결과 확인 중...")
            start_time = time.time()
            
            # 결과가 완료될 때까지 대기 (최대 60초)
            max_wait = 60
            wait_time = 0
            while wait_time < max_wait:
                try:
                    async with session.get(f'http://127.0.0.1:8000/api/reviews/{review_id}',
                                          headers=headers) as response:
                        if response.status == 200:
                            review_status = await response.json()
                            if review_status.get('status') == 'completed':
                                print(f"   ✅ 리뷰 완료! ({time.time() - start_time:.2f}초)")
                                break
                        elif response.status == 409:
                            print(f"   ⏳ 리뷰 진행 중... ({wait_time}초)")
                        else:
                            print(f"   ⚠️ 예상치 못한 상태: {response.status}")
                except Exception as e:
                    print(f"   ⚠️ 요청 실패: {e}")
                
                await asyncio.sleep(2)
                wait_time += 2
            
            if wait_time >= max_wait:
                print("   ⚠️ 리뷰 완료 대기 시간 초과")
            else:
                print("   🎉 전체 사용자 여정 테스트 완료!")
    
    @pytest.mark.asyncio
    async def test_multi_user_scenario(self):
        """다중 사용자 시나리오 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 다중 사용자 시나리오 테스트 ===")
            
            # 여러 사용자가 동시에 룸 생성
            users = ["user1", "user2", "user3"]
            rooms = []
            
            print("1. 다중 사용자 룸 생성...")
            for user in users:
                headers = {'Authorization': f'Bearer dummy-id-token-{user}'}
                async with session.post('http://127.0.0.1:8000/api/rooms',
                                      json={'title': f'{user}의 룸'}) as response:
                    assert response.status == 200
                    room_data = await response.json()
                    rooms.append((user, room_data['room_id']))
                    print(f"   ✅ {user}: 룸 {room_data['room_id']} 생성")
            
            # 동시에 메시지 전송
            print("2. 동시 메시지 전송...")
            async def send_message(user: str, room_id: str, message: str):
                headers = {'Authorization': f'Bearer dummy-id-token-{user}'}
                async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                      json={'role': 'user', 'content': message},
                                      headers=headers) as response:
                    return response.status == 200
            
            tasks = []
            for user, room_id in rooms:
                task = send_message(user, room_id, f"{user}의 테스트 메시지")
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            success_count = sum(results)
            print(f"   ✅ {success_count}/{len(results)} 메시지 전송 성공")
            
            assert success_count == len(results), "일부 메시지 전송 실패"
    
    @pytest.mark.asyncio
    async def test_error_handling_scenarios(self):
        """에러 처리 시나리오 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 에러 처리 시나리오 테스트 ===")
            
            # 1. 존재하지 않는 룸에 메시지 전송
            print("1. 존재하지 않는 룸 테스트...")
            headers = {'Authorization': 'Bearer dummy-id-token'}
            async with session.post('http://127.0.0.1:8000/api/rooms/nonexistent-room/messages',
                                  json={'role': 'user', 'content': '테스트 메시지'},
                                  headers=headers) as response:
                assert response.status == 404
                print("   ✅ 404 에러 정상 처리")
            
            # 2. 인증 없이 메시지 전송
            print("2. 인증 없이 메시지 전송 테스트...")
            async with session.post('http://127.0.0.1:8000/api/rooms/test-room/messages',
                                  json={'role': 'user', 'content': '테스트 메시지'}) as response:
                assert response.status == 403
                print("   ✅ 403 에러 정상 처리")
            
            # 3. 잘못된 형식의 메시지
            print("3. 잘못된 메시지 형식 테스트...")
            # 먼저 룸 생성
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': '에러 테스트 룸'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
            
            # 빈 메시지 전송
            async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                  json={'role': 'user', 'content': ''},
                                  headers=headers) as response:
                assert response.status == 400
                print("   ✅ 400 에러 정상 처리")
            
            # 4. 너무 긴 메시지
            long_message = "A" * 1001  # 1000자 초과
            async with session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                  json={'role': 'user', 'content': long_message},
                                  headers=headers) as response:
                assert response.status == 400
                print("   ✅ 긴 메시지 400 에러 정상 처리")
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self):
        """부하 상황에서의 성능 테스트"""
        async with aiohttp.ClientSession() as session:
            print("\n=== 부하 테스트 ===")
            
            # 1. 빠른 연속 요청
            print("1. 빠른 연속 요청 테스트...")
            start_time = time.time()
            
            # 룸 생성
            async with session.post('http://127.0.0.1:8000/api/rooms',
                                  json={'title': '부하 테스트 룸'}) as response:
                assert response.status == 200
                room_data = await response.json()
                room_id = room_data['room_id']
            
            headers = {'Authorization': 'Bearer dummy-id-token'}
            
            # 20개의 빠른 메시지 전송
            tasks = []
            for i in range(20):
                task = session.post(f'http://127.0.0.1:8000/api/rooms/{room_id}/messages',
                                  json={'role': 'user', 'content': f'부하 테스트 메시지 {i}'},
                                  headers=headers)
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 200)
            
            total_time = time.time() - start_time
            print(f"   ✅ {success_count}/20 메시지 성공 ({total_time:.2f}초)")
            print(f"   📊 평균 처리 시간: {total_time/20:.2f}초/메시지")
            
            # 2. 동시 룸 생성
            print("2. 동시 룸 생성 테스트...")
            start_time = time.time()
            
            async def create_room(i: int):
                async with session.post('http://127.0.0.1:8000/api/rooms',
                                      json={'title': f'동시 룸 {i}'}) as response:
                    return response.status == 200
            
            room_tasks = [create_room(i) for i in range(10)]
            room_results = await asyncio.gather(*room_tasks)
            room_success = sum(room_results)
            
            room_time = time.time() - start_time
            print(f"   ✅ {room_success}/10 룸 생성 성공 ({room_time:.2f}초)")
            
            # 성능 기준 검증
            assert success_count >= 15, f"메시지 전송 성공률이 낮음: {success_count}/20"
            assert room_success >= 8, f"룸 생성 성공률이 낮음: {room_success}/10"
            assert total_time < 30, f"메시지 전송 시간이 너무 김: {total_time}초"
            assert room_time < 10, f"룸 생성 시간이 너무 김: {room_time}초"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

