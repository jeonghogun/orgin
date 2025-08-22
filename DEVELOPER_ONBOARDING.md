# Origin Project 개발자 온보딩 가이드

## 🚀 빠른 시작

### 1. 프로젝트 클론 및 설정
```bash
# 프로젝트 클론
git clone <repository-url>
cd orgin

# 가상환경 설정
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정
```bash
# .env 파일 생성
cp .env.example .env

# 필수 환경 변수 설정
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CSE_ID=your_custom_search_engine_id
```

### 3. 서버 실행
```bash
# 환경 변수 설정
export PYTHONPATH=$PWD

# 서버 시작
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. 접속 확인
```
http://127.0.0.1:8000
```

## 📚 문서 읽기 순서

### 1단계: 프로젝트 개요
- **[README.md](./README.md)**: 프로젝트 전체 개요와 주요 기능
- **[PHASE_1_6_5_INTEGRATION_REPORT.md](./PHASE_1_6_5_INTEGRATION_REPORT.md)**: 상세한 기술 문서

### 2단계: 아키텍처 이해
- **프로젝트 구조**: `app/` 폴더 구조 파악
- **서비스 레이어**: 각 서비스의 역할과 관계
- **데이터 플로우**: 사용자 입력부터 AI 응답까지의 흐름

### 3단계: 개발 환경 설정
- **IDE 설정**: VS Code 추천 설정
- **코드 품질 도구**: Pyright, Black, Flake8
- **테스트 환경**: pytest 설정

## 🏗️ 아키텍처 이해

### 핵심 컴포넌트
```
사용자 입력 → IntentService → MemoryService → RAGService → AI 응답
     ↓              ↓              ↓              ↓
  Chat UI    의도 분류      맥락 관리    외부 정보 통합
```

### 주요 서비스들
1. **IntentService**: 사용자 메시지 의도 분류
2. **MemoryService**: 대화 맥락 및 사용자 프로필 관리
3. **RAGService**: 외부 정보를 활용한 응답 생성
4. **ExternalSearchService**: Google Search, Wikipedia API

## 🔧 개발 워크플로우

### 1. 기능 개발
```bash
# 1. 브랜치 생성
git checkout -b feature/new-feature

# 2. 코드 작성
# 3. 테스트 작성
pytest tests/unit/test_new_feature.py

# 4. 코드 품질 검사
pyright app/
black app/
flake8 app/

# 5. 커밋 및 푸시
git add .
git commit -m "feat: add new feature"
git push origin feature/new-feature
```

### 2. 버그 수정
```bash
# 1. 이슈 확인
# 2. 브랜치 생성
git checkout -b fix/bug-description

# 3. 수정 및 테스트
# 4. PR 생성
```

## 🧪 테스트

### 테스트 실행
```bash
# 전체 테스트
pytest tests/

# 단위 테스트만
pytest tests/unit/

# 통합 테스트만
pytest tests/integration/

# 특정 테스트 파일
pytest tests/unit/test_intent_service.py

# 커버리지 포함
pytest --cov=app tests/
```

### 테스트 작성 가이드
```python
# tests/unit/test_new_service.py
import pytest
from app.services.new_service import NewService

class TestNewService:
    @pytest.fixture
    def service(self):
        return NewService()
    
    def test_some_function(self, service):
        result = service.some_function("test")
        assert result == "expected"
```

## 🔍 디버깅

### 로그 확인
```bash
# 애플리케이션 로그
tail -f logs/app.log

# uvicorn 로그
tail -f uvicorn.log
```

### API 테스트
```bash
# 헬스 체크
curl http://127.0.0.1:8000/health

# 메시지 전송 테스트
curl -X POST http://127.0.0.1:8000/api/rooms/test-room/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "안녕하세요"}'
```

### 환경 변수 디버그
```bash
curl http://127.0.0.1:8000/api/debug/env
```

## 📝 코딩 컨벤션

### Python 코드 스타일
- **Black**: 코드 포맷팅
- **Pyright**: 타입 체크
- **Flake8**: 린팅

### 네이밍 컨벤션
- **클래스**: PascalCase (예: `IntentService`)
- **함수/변수**: snake_case (예: `classify_intent`)
- **상수**: UPPER_SNAKE_CASE (예: `MAX_RETRIES`)

### 문서화
```python
async def some_function(param: str) -> Dict[str, Any]:
    """
    함수 설명
    
    Args:
        param: 매개변수 설명
        
    Returns:
        반환값 설명
        
    Raises:
        ExceptionType: 예외 설명
    """
    pass
```

## 🚨 주의사항

### 1. API 키 관리
- `.env` 파일을 절대 커밋하지 마세요
- API 키는 환경 변수로 관리
- 프로덕션에서는 시크릿 매니저 사용

### 2. 데이터베이스
- SQLite는 개발용, 프로덕션에서는 PostgreSQL 사용
- Redis는 선택사항이지만 캐싱 성능 향상에 도움

### 3. 외부 API
- Google Custom Search: 일일 쿼리 제한 (10,000회)
- OpenAI API: 요청당 비용 발생
- Wikipedia API: 무료이지만 요청 제한 있음

## 📞 도움말

### 문제 해결
1. **서버 시작 안됨**: 포트 8000이 사용 중인지 확인
2. **API 키 오류**: 환경 변수 설정 확인
3. **의존성 오류**: `pip install -r requirements.txt` 재실행

### 추가 문서
- **[Phase 1-6.5 통합 보고서](./PHASE_1_6_5_INTEGRATION_REPORT.md)**: 상세 기술 문서
- **[API 문서](http://127.0.0.1:8000/docs)**: Swagger UI
- **[North Star 갭 분석](./NORTH_STAR_GAP_ANALYSIS.md)**: 아키텍처 목표

### 커뮤니케이션
- **이슈 리포트**: GitHub Issues 사용
- **코드 리뷰**: PR 생성 시 리뷰어 지정
- **문서 업데이트**: 기능 추가 시 관련 문서도 업데이트

---

**Happy Coding! 🚀**
