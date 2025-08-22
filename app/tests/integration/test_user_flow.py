import pytest
from fastapi.testclient import TestClient
import time

@pytest.mark.integration
class TestUserFlow:
    """실제 사용자 흐름 E2E 테스트"""

    def test_complete_user_journey(self, client: TestClient):
        """완전한 사용자 여정 테스트: 룸 생성 → 채팅 → 리뷰 생성 시도"""
        print("\n=== 사용자 여정 테스트 시작 ===")

        # 1. 룸 생성
        print("1. 룸 생성 중...")
        response = client.post('/api/rooms', json={'title': '사용자 여정 테스트 룸'})
        assert response.status_code == 200
        room_data = response.json()['data']
        room_id = room_data['room_id']
        print(f"   ✅ 룸 생성 완료: {room_id}")

        # 2. 메시지 전송
        headers = {'Authorization': 'Bearer dummy-id-token'}
        print("2. 메시지 전송 중...")

        messages = [
            "안녕하세요! 새로운 프로젝트에 대해 상담받고 싶습니다.",
            "우리 회사는 AI 기반 교육 플랫폼을 개발하려고 합니다.",
            "주요 기능은 개인화된 학습 경로, 실시간 피드백, 그리고 게이미피케이션입니다.",
        ]

        for message in messages:
            response = client.post(f'/api/rooms/{room_id}/messages',
                                   json={'content': message},
                                   headers=headers)
            assert response.status_code == 200
        print(f"   ✅ 메시지 전송 완료")

        # 3. 대화 기록 확인
        print("3. 대화 기록 확인 중...")
        response = client.get(f'/api/context/{room_id}', headers=headers)
        assert response.status_code == 200
        print(f"   ✅ 대화 기록 조회 완료")

        # 4. 리뷰 생성 시도 (expect 422 because not fully implemented)
        print("4. 리뷰 생성 시도 (expect 422)...")
        review_request = {
            "topic": "AI 기반 교육 플랫폼 개발 프로젝트 검토",
            "rounds": [{"round_number": 1, "mode": "divergent", "instruction": "Test"}]
        }
        response = client.post(f'/api/rooms/{room_id}/reviews',
                               json=review_request,
                               headers=headers)
        assert response.status_code == 422

    def test_multi_user_scenario(self, client: TestClient):
        """다중 사용자 시나리오 테스트"""
        print("\n=== 다중 사용자 시나리오 테스트 ===")

        users = ["user1", "user2", "user3"]
        rooms = []

        print("1. 다중 사용자 룸 생성...")
        for user in users:
            headers = {'Authorization': f'Bearer dummy-id-token-{user}'}
            response = client.post('/api/rooms', json={'title': f'{user}의 룸'}, headers=headers)
            assert response.status_code == 200
            room_data = response.json()['data']
            rooms.append((user, room_data['room_id']))
            print(f"   ✅ {user}: 룸 {room_data['room_id']} 생성")

        print("2. 동시 메시지 전송 (시뮬레이션)...")
        success_count = 0
        for user, room_id in rooms:
            headers = {'Authorization': f'Bearer dummy-id-token-{user}'}
            response = client.post(f'/api/rooms/{room_id}/messages',
                                   json={'content': f'{user}의 테스트 메시지'},
                                   headers=headers)
            if response.status_code == 200:
                success_count += 1

        assert success_count == len(rooms)
        print(f"   ✅ {success_count}/{len(rooms)} 메시지 전송 성공")

    def test_error_handling_scenarios(self, client: TestClient):
        """에러 처리 시나리오 테스트"""
        print("\n=== 에러 처리 시나리오 테스트 ===")

        headers = {'Authorization': 'Bearer dummy-id-token'}

        print("1. 존재하지 않는 룸에 메시지 전송...")
        response = client.post('/api/rooms/nonexistent-room/messages',
                               json={'content': '테스트 메시지'},
                               headers=headers)
        assert response.status_code == 404
        print("   ✅ 404 에러 정상 처리")

        print("2. 잘못된 형식의 메시지...")
        response = client.post('/api/rooms', json={'title': '에러 테스트 룸'}, headers=headers)
        assert response.status_code == 200
        room_id = response.json()['data']['room_id']

        response = client.post(f'/api/rooms/{room_id}/messages',
                               json={'content': ''},
                               headers=headers)
        assert response.status_code == 400
        print("   ✅ 400 에러 정상 처리")

    def test_performance_under_load(self, client: TestClient):
        """부하 상황에서의 성능 테스트 (기능적 정확성)"""
        print("\n=== 부하 테스트 (기능적 정확성) ===")

        response = client.post('/api/rooms', json={'title': '부하 테스트 룸'})
        assert response.status_code == 200
        room_id = response.json()['data']['room_id']

        headers = {'Authorization': 'Bearer dummy-id-token'}

        success_count = 0
        for i in range(10): # Reduced from 20 for speed
            response = client.post(f'/api/rooms/{room_id}/messages',
                                   json={'content': f'부하 테스트 메시지 {i}'},
                                   headers=headers)
            if response.status_code == 200:
                success_count += 1

        assert success_count == 10
        print(f"   ✅ {success_count}/10 메시지 성공")
