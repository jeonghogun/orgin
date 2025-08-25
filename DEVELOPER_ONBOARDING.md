# Origin Project 개발자 온보딩 가이드

## 🚀 빠른 시작

### 1. 프로젝트 클론 및 설정
```bash
# 프로젝트 클론
git clone <repository-url>
cd origin

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
# FIREBASE_SERVICE_ACCOUNT_PATH=path/to/your/firebase-credentials.json # (선택 사항)
```

### 3. 서버 실행
```bash
# PYTHONPATH 설정 (중요: 프로젝트 루트에서 실행)
export PYTHONPATH=$PWD

# 서버 시작
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. 접속 확인
```
http://127.0.0.1:8000
```

## 📚 문서 읽기 순서

1.  **[README.md](./README.md)**: 프로젝트 전체 개요와 주요 기능
2.  **[PHASE_1_6_5_INTEGRATION_REPORT.md](./PHASE_1_6_5_INTEGRATION_REPORT.md)**: 상세한 기술 문서 (과거 기록)

## 🏗️ 아키텍처 이해

### 핵심 컴포넌트
- **Rooms & Hierarchy**: `Main` > `Sub` > `Review` 룸 계층 구조
- **Services**: 각 기능별 비즈니스 로직 (e.g., `ReviewService`, `StorageService`)
- **API**: FastAPI를 사용한 RESTful API 엔드포인트
- **Frontend**: `app/frontend`에 위치한 Vanilla JS 기반 SPA

## 🔧 개발 워크플로우

### 1. 기능 개발
```bash
# 1. 브랜치 생성
git checkout -b feature/new-feature

# 2. 코드 작성 (Python 백엔드, JS 프론트엔드)

# 3. 테스트 작성 및 실행
export PYTHONPATH=$PWD
pytest tests/

# 4. 코드 품질 검사
black .
flake8 app tests
pyright .

# 5. 커밋 및 푸시
git commit -m "feat: Add new feature"
git push origin feature/new-feature
```

## 🧪 테스트

### 테스트 실행
```bash
# 전체 테스트 실행 (PYTHONPATH 설정 필수)
export PYTHONPATH=$PWD
pytest tests/

# 특정 테스트 파일 실행
export PYTHONPATH=$PWD
pytest tests/integration/api/test_rooms_api.py
```

### 테스트 작성 가이드
- **백엔드 API 테스트**: `fastapi.testclient.TestClient`를 사용합니다. (`tests/integration/api/` 참고)
- **서비스 로직 테스트**: `unittest.mock`을 사용하여 의존성을 모킹합니다. (`tests/unit/services/` 참고)
- **비동기 테스트**: `@pytest.mark.anyio` 데코레이터를 사용합니다.

## 🚨 주의사항

### 1. API 키 관리
- `.env` 파일을 절대 커밋하지 마세요.
- API 키는 환경 변수로 관리합니다.

### 2. 데이터베이스
- 기본 저장소는 로컬 파일 시스템(`data/` 디렉토리)입니다.
- `FIREBASE_SERVICE_ACCOUNT_PATH` 환경 변수를 설정하면 Firebase Firestore를 데이터베이스로 사용합니다.
- Redis 캐싱은 현재 구현되어 있지 않습니다.

### 3. 외부 API
- Google Custom Search: 일일 쿼리 제한 있음.
- OpenAI API: 요청당 비용 발생.

## 📞 도움말

### 문제 해결
1. **서버 시작 안됨**: 포트 8000이 사용 중인지 확인 (`lsof -i :8000`)
2. **API 키 오류**: `.env` 파일에 환경 변수가 올바르게 설정되었는지 확인
3. **ImportError**: `export PYTHONPATH=$PWD`를 실행했는지 확인

### 추가 문서
- **[API 문서](http://127.0.0.1:8000/docs)**: Swagger UI

---

**Happy Coding! 🚀**
