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
pip install -r requirements-dev.txt
```

### 2. 시스템 의존성 설치 (테스트 및 전체 기능)
로컬 개발 및 테스트를 위해서는 다음 시스템 패키지가 필요합니다.

**macOS (Homebrew 사용):**
```bash
brew install postgresql@15
brew install redis
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install postgresql-15 postgresql-contrib-15
sudo apt-get install redis-server
```
**PostgreSQL 설정:**
설치 후, `pgvector` 확장을 활성화해야 합니다.
```sql
-- psql에 접속하여 실행
CREATE EXTENSION pgvector;
```

### 3. 환경 변수 설정
```bash
# .env 파일 생성
cp .env.example .env

# 필수 환경 변수 설정
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CSE_ID=your_custom_search_engine_id
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/dbname
REDIS_URL=redis://localhost:6379/0
# FIREBASE_SERVICE_ACCOUNT_PATH=path/to/your/firebase-credentials.json # (더 이상 사용되지 않음)
```

### 4. 서버 실행
```bash
# PYTHONPATH 설정 (중요: 프로젝트 루트에서 실행)
export PYTHONPATH=$PWD

# 서버 시작
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. 접속 확인
```
http://127.0.0.1:8000
```

## 📚 문서 읽기 순서

1.  **[README.md](./README.md)**: 프로젝트 전체 개요와 주요 기능
2.  **[PHASE_1_6_5_INTEGRATION_REPORT.md](./PHASE_1_6_5_INTEGRATION_REPORT.md)**: 상세한 기술 문서 (과거 기록)

## 🏗️ 아키텍처 이해

### 핵심 컴포넌트
- **Services**: 각 기능별 비즈니스 로직 (e.g., `ReviewService`, `StorageService`, `LLMService`). 서비스는 FastAPI의 의존성 주입(Dependency Injection)을 통해 관리됩니다.
- **API**: FastAPI를 사용한 RESTful API 엔드포인트
- **Async Tasks**: Celery를 사용하여 리뷰 생성과 같은 오래 걸리는 작업을 비동기적으로 처리합니다.
- **Database**: PostgreSQL과 pgvector 확장을 사용하여 구조화된 데이터와 벡터 임베딩을 저장합니다.
- **Cache & Message Broker**: Redis를 사용하여 캐싱 및 Celery 메시지 브로커 역할을 수행합니다.
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
pyright app
```

### 5. 커밋 및 푸시
```bash
git commit -m "feat: Add new feature"
git push origin feature/new-feature
```

## 🧪 테스트

### 테스트 실행
테스트를 실행하기 전에 **PostgreSQL과 Redis 서버가 실행 중**인지 확인하세요.

```bash
# 전체 테스트 실행 (PYTHONPATH 설정 필수)
export PYTHONPATH=$PWD
pytest tests/

# 특정 테스트 파일 실행
export PYTHONPATH=$PWD
pytest tests/integration/api/test_reviews_api.py
```

### 테스트 작성 가이드
- **백엔드 API 테스트**: `fastapi.testclient.TestClient`를 사용합니다. (`tests/integration/api/` 참고)
- **서비스 로직 테스트**: `unittest.mock`을 사용하여 의존성을 모킹합니다. (`tests/unit/services/` 참고)
- **비동기 테스트**: `@pytest.mark.anyio` 데코레이터를 사용합니다.
- **데이터베이스 의존 테스트**: `testing.postgresql` 라이브러리를 사용하여 테스트 실행 시 임시 데이터베이스를 생성하고 관리합니다.

## 🚨 주의사항

### 1. API 키 관리
- `.env` 파일을 절대 커밋하지 마세요.
- API 키는 환경 변수로 관리합니다.

### 2. 데이터베이스
- **주 저장소**: PostgreSQL 데이터베이스를 사용합니다. `DATABASE_URL` 환경 변수를 설정해야 합니다.
- **벡터 검색**: `pgvector` 확장을 사용하여 벡터 임베딩을 저장하고 검색합니다.
- **캐싱 및 메시징**: Redis를 사용합니다. `REDIS_URL` 환경 변수를 설정해야 합니다.
- `data/` 디렉토리와 Firebase Firestore는 더 이상 기본 데이터베이스로 사용되지 않습니다.

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
