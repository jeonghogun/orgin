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

### 2. Docker 기반 개발 환경 실행
이 프로젝트는 모든 서비스(PostgreSQL, Redis, API, Workers, Frontend)를 컨테이너화하여 일관된 개발 환경을 제공합니다. 로컬에 별도의 데이터베이스나 Redis를 설치할 필요가 없습니다.

**필수 사전 조건:**
- [Docker](https://www.docker.com/products/docker-desktop/)가 설치되어 있어야 합니다.

**실행 단계:**
```bash
# 1. 환경 변수 파일 생성
# .env.example 파일을 복사하여 .env 파일을 만들고, 필수 키를 채웁니다.
cp .env.example .env

# 2. Docker Compose로 모든 서비스 시작
docker-compose up --build
```

### 3. 데이터베이스 마이그레이션 (Database Migration)
이 프로젝트는 Alembic을 사용하여 데이터베이스 스키마를 관리합니다. `docker-compose up`으로 서비스를 처음 실행한 후, 또는 데이터베이스 스키마에 변경이 있을 때마다 다음 명령어를 실행하여 최신 상태로 마이그레이션해야 합니다.

새로운 터미널에서 다음 명령어를 실행하세요:
```bash
# 실행 중인 api 컨테이너 내부에서 alembic upgrade 명령 실행
docker-compose exec api alembic upgrade heads
```

**새로운 마이그레이션 생성하기:**
데이터베이스 스키마를 직접 변경해야 하는 경우, 다음 명령어로 새로운 마이그레이션 스크립트를 생성할 수 있습니다.
```bash
# api 컨테이너 내부에서 실행
docker-compose exec api alembic revision --autogenerate -m "A short description of the changes"
```
> **참고**: 이 프로젝트는 SQLAlchemy ORM을 사용하지 않으므로, `autogenerate`가 모든 변경사항을 감지하지 못할 수 있습니다. 생성된 마이그레이션 스크립트를 직접 검토하고 수정해야 할 수 있습니다.

### 4. 접속 확인
- **Frontend (Nginx)**: `http://localhost:8080`
- **API (직접 접속)**: `http://localhost:8000`
- **API 문서 (Swagger)**: `http://localhost:8000/docs`

## 📚 문서 읽기 순서

1.  **[README.md](./README.md)**: 프로젝트 전체 개요와 주요 기능
2.  **[PHASE_1_6_5_INTEGRATION_REPORT.md](./PHASE_1_6_5_INTEGRATION_REPORT.md)**: 상세한 기술 문서 (과거 기록)

## 🏗️ 아키텍처 이해

### 핵심 컴포넌트
- **Services**: 각 기능별 비즈니스 로직 (e.g., `ReviewService`, `StorageService`, `LLMService`). 서비스는 FastAPI의 의존성 주입(Dependency Injection)을 통해 관리됩니다.
- **API**: FastAPI를 사용한 RESTful API 엔드포인트
- **Async Tasks**: Celery를 사용하여 리뷰 생성과 같은 오래 걸리는 작업을 비동기적으로 처리합니다. `review_tasks.py`의 핵심 로직은 가독성과 유지보수성을 위해 작은 함수들로 리팩토링되었습니다.
- **Database**: PostgreSQL과 pgvector 확장을 사용하여 구조화된 데이터와 벡터 임베딩을 저장합니다.
- **Cache & Message Broker**: Redis를 사용하여 캐싱 및 Celery 메시지 브로커 역할을 수행합니다.
- **Frontend**: `app/frontend`에 위치한 React (Vite) 기반 SPA. `@tanstack/react-query`를 사용하여 서버 상태를 관리하고, 데이터 페칭, 캐싱, 동기화를 처리합니다.

### 데이터 저장소 아키텍처
모든 데이터는 PostgreSQL에 통합되어 관리됩니다. 더 이상 하이브리드 모델이나 SQLite를 사용하지 않습니다.

- **PostgreSQL**: 사용자, 룸, 메시지, 리뷰, 메모리, 사용자 프로필 등 모든 데이터를 저장합니다.
  - `pgvector`: 의미 검색을 위한 벡터 임베딩 저장 및 쿼리
  - `pgcrypto`: 민감한 사용자 데이터 필드 암호화

## 🔧 개발 워크플로우

### 1. 기능 개발 (Docker 내부에서)
Docker 컨테이너가 실행 중인 상태에서, 로컬 파일 시스템의 변경사항은 컨테이너 내부에 실시간으로 반영됩니다 (volumes 마운트).

- **백엔드 변경**: `app/` 디렉토리의 파일을 수정하면 `uvicorn`이 자동으로 재시작합니다.
- **프론트엔드 변경**: `app/frontend/` 디렉토리의 파일을 수정하면 Vite 개발 서버가 즉시 변경사항을 반영합니다.

### 2. 테스트 실행 (Docker 내부에서)
새로운 터미널을 열고 실행 중인 API 서버 컨테이너 내부에서 테스트를 실행할 수 있습니다.
```bash
# 실행 중인 api 컨테이너의 ID 또는 이름 찾기
docker ps

# 컨테이너 내부에서 전체 테스트 실행
docker exec -it <api_container_name_or_id> pytest tests/
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
- **디버깅 팁**: 모든 로그에는 `trace_id`가 포함되어 있어, 특정 요청의 전체 흐름을 추적하는 데 사용할 수 있습니다.

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

## ⚙️ 주요 설정 (Key Configurations)
`.env` 파일을 통해 다음의 주요 기능들을 활성화하거나 튜닝할 수 있습니다.

- **하이브리드 검색 (Hybrid Retrieval):**
  - `HYBRID_BM25_WEIGHT`: BM25 (텍스트 검색) 점수 가중치 (기본값: 0.55)
  - `HYBRID_VEC_WEIGHT`: Vector (의미 검색) 점수 가중치 (기본값: 0.45)
  - `TIME_DECAY_ENABLED`: 시간에 따른 점수 감소 활성화 여부 (기본값: True)

- **리랭커 (Re-ranker):**
  - `RERANK_ENABLED`: 검색 결과 재정렬 기능 활성화 여부 (기본값: False)
  - `RERANK_PROVIDER`: 사용할 리랭커 제공자 (예: "cohere")

## ⚠️ 알려진 문제 (Known Issues)

### 1. `requirements-dev.txt` 설치 오류
**문제**: `pip install -r requirements-dev.txt` 실행 시, 간헐적으로 `[Errno 2] No such file or directory` 오류가 발생할 수 있습니다. 이는 파일이 존재하고 읽기 가능함에도 불구하고 발생하는 환경 특정적인 문제입니다.

**임시 해결책**: 이 문제가 발생하면, 현재로서는 이 단계를 건너뛰고 Docker 기반 개발 환경을 사용하세요. Docker 환경은 필요한 모든 의존성을 포함하고 있습니다. 이 문제는 별도로 추적 및 해결될 예정입니다.

---

**Happy Coding! 🚀**
