# 진행 로그 (Progress Log)

이 문서는 Origin 프로젝트 품질 안정화 작업의 진행 상황을 시간순으로 기록합니다.

---

### 2025-09-14

- **Task Received:** 사용자로부터 프로젝트 품질 안정화 및 종합 리포트 작성에 대한 신규 지시사항을 받음. 기존 분석 작업을 중단하고 새로운 목표에 맞춰 작업 계획을 재수립.
- **Setup:** `REPORT_project_status.md`, `TEST_ENV_DESIGN.md`, `PROGRESS.md`, `TECH_DEBT_PROPOSALS.md` 등 최종 제출물 파일들의 플레이스홀더를 생성함.
- **Next Step:** P0 최우선 과제인 Alembic 마이그레이션의 SQLite 호환성 확보 작업을 시작할 예정.

### 2025-09-14 (Continued)
- **Task: P0 - Alembic Migration Compatibility**
  - **Problem:** `alembic/versions/` 내 마이그레이션 파일들이 PostgreSQL 전용 DDL(e.g., `CREATE EXTENSION`, `ALTER COLUMN`)을 포함하고 있어 SQLite 환경에서 실패함.
  - **Investigation:** `37ecae34152b_...` 과 `4f2a569fdcc5_...` 파일을 주요 문제 파일로 식별함.
  - **Solution:** `37ecae34152b_...` 파일의 PostgreSQL 전용 구문을 `if bind.dialect.name == 'postgresql':` 블록으로 래핑함. `4f2a569fdcc5_...` 파일의 `op.alter_column` 등 SQLite에서 호환되지 않는 명령어를 `op.batch_alter_table()` 컨텍스트 매니저를 사용하도록 리팩토링함.
  - **Files Changed:** `alembic/versions/37ecae34152b_create_initial_tables_from_schema_sql.py`, `alembic/versions/4f2a569fdcc5_encrypt_message_content.py`

- **Task: P0 - ORM Schema Synchronization**
  - **Problem:** `app/models/orm_models.py` 가 실제 DB 스키마와 불일치하는 P0 이슈가 있었음.
  - **Investigation:** 이전 작업에서 생성한 ORM 모델 파일과, 호환성 수정이 완료된 마이그레이션 파일들의 최종 스키마 상태를 비교 검토함.
  - **Solution:** 마이그레이션 호환성 수정 작업이 최종 스키마 구조에 영향을 주지 않았음을 확인. 이전에 수정한 `orm_models.py`가 이미 정확한 상태이므로 추가 변경은 불필요.
  - **Files Changed:** (None, verification only)

- **Task: P0 - StorageService Transaction Integrity**
  - **Problem:** `StorageService`의 `save_message` 메서드가 두 개의 분리된 쓰기 작업을 수행하여 데이터 정합성을 해칠 위험이 있었음.
  - **Investigation:** `app/services/database_service.py`에 이미 `transaction` 컨텍스트 매니저가 구현되어 있음을 발견.
  - **Solution:** `save_message` 메서드를 리팩토링하여 두 쓰기 작업을 `with self.db.transaction(...)` 블록으로 묶어 원자성을 보장함. 서비스 내 다른 메서드들은 단일 쿼리이므로 추가 수정 불필요.
  - **Files Changed:** `app/services/storage_service.py`

- **Task: P1 - Prompt Externalization**
  - **Problem:** `app/tasks/review_tasks.py`에 AI 프롬프트가 하드코딩되어 유지보수가 어려웠음.
  - **Investigation:** 4개의 주요 프롬프트를 식별함.
  - **Solution:**
    1. `app/prompts/` 디렉토리 생성.
    2. 4개의 프롬프트 템플릿 파일(.txt) 생성.
    3. 템플릿을 로드하고 포맷하는 `app/services/prompt_service.py` 생성.
    4. `review_tasks.py`를 리팩토링하여 `prompt_service`를 사용하도록 변경.
  - **Files Changed:** `app/tasks/review_tasks.py`, `app/services/prompt_service.py`, `app/prompts/*.txt`

- **Task: P1 - LLM Output Validation**
  - **Problem:** LLM이 반환하는 JSON의 구조적 무결성을 보장하는 장치가 없었음.
  - **Solution:**
    1. LLM의 각 라운드별 출력에 대한 Pydantic 모델을 `app/models/review_schemas.py`에 정의.
    2. `review_tasks.py`의 `_process_turn_results` 헬퍼 함수를 리팩토링하여 Pydantic 모델로 유효성 검사를 수행하도록 변경.
    3. 모든 태스크가 이 검증 로직을 사용하도록 업데이트.
  - **Files Changed:** `app/tasks/review_tasks.py`, `app/models/review_schemas.py`

- **Task: P0 - Test Suite Execution & Documentation**
  - **Problem:** `scripts/run_tests.sh` 실행 시 `pytest` 모듈이 없다는 에러 발생.
  - **Investigation:** `requirements-dev.txt`에 테스트 의존성이 정의되어 있음을 확인.
  - **Action:** `pip install -r requirements-dev.txt` 실행했으나 샌드박스 환경의 시간 초과(timeout)로 인해 실패함.
  - **Workaround:** 의존성 설치가 불가능하므로, 테스트 환경 문서를 작성하는 것으로 방향 전환. `docker-compose.test.yml` 파일을 분석하여 로컬 테스트 환경에 PostgreSQL과 Redis가 필요함을 확인함.
  - **Solution:** 로컬 환경에서 Docker를 사용하여 전체 테스트를 실행하는 상세 가이드를 `TEST_ENV_DESIGN.md`에 작성함. 가이드에는 사전 요구사항, 단계별 명령어, `.env` 샘플, 샌드박스 제약사항에 대한 설명이 포함됨.
  - **Files Changed:** `TEST_ENV_DESIGN.md`

- **Task: P1/P2 - Final Code Cleanup (CORS)**
  - **Problem:** `app/main.py`에 CORS 정책이 와일드카드(`*`)로 설정되어 있어 보안에 취약했음.
  - **Investigation:** `app/config/settings.py`에 관련 설정이 없음을 확인.
  - **Solution:**
    1. `settings.py`에 `CORS_ALLOWED_ORIGINS` 변수를 추가하고, 로컬 개발 환경에 적합한 기본값을 설정함.
    2. `main.py`의 `CORSMiddleware`가 이 설정을 읽어오도록 수정하여, 허용된 출처를 환경 변수로 제어할 수 있게 함.
  - **Files Changed:** `app/config/settings.py`, `app/main.py`

### 2025-09-14 (Phase 2.5)
- **Task: P0 - Observability Design & Implementation**
  - **Problem:** 프로젝트의 로그, 메트릭, 트레이스가 분산되어 있어 통합적인 관리가 어려웠음.
  - **Investigation:** PLG, ELK, OpenTelemetry 스택을 비교 분석함. 벤더 중립적이고 통합적인 OpenTelemetry를 최적의 솔루션으로 결정함.
  - **Solution:**
    1. `OBSERVABILITY_DESIGN.md` 문서를 작성하여 기술 스택 선택의 근거와 아키텍처를 제시함.
    2. `requirements-dev.txt`에 OpenTelemetry 관련 의존성을 추가함.
    3. `app/core/telemetry.py`에 콘솔 출력을 기본으로 하는 OpenTelemetry SDK 설정 코드를 구현함.
    4. `app/main.py`의 `lifespan`에서 `setup_telemetry()`를 호출하여 애플리케이션 시작 시 계측이 활성화되도록 함.
    5. `README.md`에 `opentelemetry-instrument`를 사용한 실행 방법을 추가하여 개발자 가이드를 업데이트함.
  - **Files Changed:** `OBSERVABILITY_DESIGN.md`, `requirements-dev.txt`, `app/core/telemetry.py`, `app/main.py`, `README.md`

- **Task: P1 - Advanced Prompt Management**
  - **Problem:** 단순 `.txt` 파일 기반의 프롬프트 시스템은 버전 관리 및 A/B 테스트에 한계가 있었음.
  - **Solution:**
    1. 버전 관리 및 메타데이터를 포함할 수 있는 YAML 기반 프롬프트 스키마를 `PROMPT_MANAGEMENT.md`에 설계함.
    2. `PyYAML` 의존성을 `requirements-dev.txt`에 추가함.
    3. 모든 프롬프트를 `app/prompts/prompts.yml` 단일 파일로 통합하고, 기존 `.txt` 파일들을 삭제함.
    4. `app/services/prompt_service.py`를 리팩토링하여 YAML 파일을 파싱하고, 버전(`default_version` 포함)에 따라 적절한 프롬프트 템플릿을 반환하도록 수정함.
  - **Files Changed:** `PROMPT_MANAGEMENT.md`, `requirements-dev.txt`, `app/prompts/prompts.yml`, `app/services/prompt_service.py`, `app/prompts/*.txt` (deleted)

- **Task: P1 - UX Improvements**
  - **Problem:** `alert()`를 사용한 에러 처리, 부재한 로딩 상태 표시 등 UX가 다소 투박했음.
  - **Solution:**
    1. `UX_IMPROVEMENTS.md` 문서를 작성하여 개선안을 설계함.
    2. `react-hot-toast` 라이브러리를 추가하고, `App.jsx`의 모든 `alert()` 호출을 비차단적인 `toast.error()`로 교체함.
    3. 로딩 상태를 시각적으로 표현하기 위한 재사용 가능한 `Skeleton.jsx` 컴포넌트와 CSS를 구현함.
    4. 프론트엔드에 WebSocket 연결 로직이 구현되어 있지 않은 현황을 발견하고, `UX_IMPROVEMENTS.md`에 이를 해결하기 위한 구체적인 구현 계획을 제안함.
  - **Files Changed:** `UX_IMPROVEMENTS.md`, `app/frontend/package.json`, `app/frontend/src/main.jsx`, `app/frontend/src/App.jsx`, `app/frontend/src/components/common/Skeleton.jsx`, `app/frontend/src/components/common/Skeleton.css`

- **Task: P1 - Security Assessment**
  - **Problem:** `content_searchable` 컬럼에 메시지 평문을 저장하는 방식의 보안 리스크 분석이 필요했음.
  - **Investigation:** 검색 가능한 대칭 암호(SSE), 토큰화+해싱, 동형 암호 등 암호학적 대안을 조사함.
  - **Solution:** 각 기술의 장단점과 현실성을 비교 분석한 `SECURITY_ASSESSMENT.md` 문서를 작성함. 단기적으로는 현재의 리스크를 인지하고 관리하되, 장기적으로는 SSE 도입을 검토하는 것을 권장함.
  - **Files Changed:** `SECURITY_ASSESSMENT.md`

- **Task: P2 - CI/CD Enhancement**
  - **Problem:** 기존 CI 워크플로우가 테스트 자동화, Docker 빌드, 마이그레이션 검증 등 핵심적인 검증 단계를 포함하고 있지 않았음.
  - **Solution:**
    1. `CICD_ENHANCEMENT.md`에 개선된 파이프라인 구조를 설계하고 문서화함.
    2. `.github/workflows/ci.yml`을 리팩토링하여 `migration-check` 잡과 `build-docker` 잡을 추가함.
    3. `test` 잡이 로컬 테스트 환경(`docker-compose.test.yml`)과 일관성을 갖도록 서비스 설정과 실행 스크립트를 수정함.
  - **Files Changed:** `CICD_ENHANCEMENT.md`, `.github/workflows/ci.yml`

### 2025-09-14 (Phase 3)
- **Task: P0 - RAG Feature Completion**
  - **Problem:** RAG(Retrieval-Augmented Generation)의 핵심인 시맨틱 검색을 위한 메시지 임베딩 생성 로직이 누락되어 있었음.
  - **Investigation:** `llm_service.py`에 임베딩 생성 함수가 이미 존재함을 확인. `rag_service.py`에서는 첨부파일에 대한 임베딩을 이미 처리하고 있었으나, 일반 메시지에 대한 처리는 부재했음.
  - **Solution:**
    1. 텍스트를 받아 임베딩을 생성하고 DB에 저장하는 비동기 Celery 태스크(`app/tasks/embedding_tasks.py`)를 신규 생성함.
    2. `storage_service.py`에 생성된 임베딩을 DB에 업데이트하는 `save_embedding` 메서드를 추가함.
    3. `storage_service.py`의 `save_message` 메서드를 수정하여, 메시지 저장 트랜잭션이 성공한 후 비동기적으로 임베딩 생성 태스크를 호출하도록 함.
    4. `hybrid_search_service.py`를 검토하여, 생성된 임베딩이 하이브리드 검색 로직에서 정상적으로 활용될 수 있는 구조임을 최종 확인함.
  - **Files Changed:** `app/tasks/embedding_tasks.py`, `app/services/storage_service.py`

- **Task: P1 - Observability Enhancement**
  - **Problem:** OpenTelemetry 구현이 콘솔 출력에만 머물러 있어 운영 환경에 적용하기 어려웠음.
  - **Investigation:** OTLP(OpenTelemetry Protocol)를 통해 외부 수집기와 연동하는 표준적인 방식을 조사함.
  - **Solution:**
    1. `settings.py`에 `OTEL_EXPORTER_OTLP_ENDPOINT` 환경 변수 설정을 추가함.
    2. `telemetry.py`를 리팩토링하여, 해당 환경 변수가 설정된 경우 OTLP Exporter를 사용하고, 그렇지 않으면 기존의 Console Exporter를 사용하도록 함.
    3. Celery 태스크(`embedding_tasks.py`)에 로그를 추가하여, 분산 추적 컨텍스트가 정상적으로 전파되는지 검증할 수 있는 코드를 추가함.
  - **Files Changed:** `app/config/settings.py`, `app/core/telemetry.py`, `app/tasks/embedding_tasks.py`

- **Task: P1 - WebSocket Real-time Feature Implementation**
  - **Problem:** 코드 리뷰를 통해 이전에 누락했던 WebSocket UX 구현이 지적됨. 프론트엔드에 실시간 기능이 활성화되지 않았었음.
  - **Investigation:** 기존에 존재하지만 사용되지 않던 `useWebSocket.js` 훅을 발견. `AuthContext`가 없다는 사실도 확인함.
  - **Solution:**
    1. `MessageList.jsx`를 리팩토링하여 `useWebSocket` 훅을 사용하도록 수정. 인증 토큰은 `null`로 전달하여 `AUTH_OPTIONAL` 설정에 의존하도록 함.
    2. WebSocket을 통해 받은 실시간 메시지를 React Query 캐시에 업데이트하여 UI에 반영하는 로직을 구현함.
    3. 연결 상태(`reconnecting` 등)를 표시하는 `ConnectionStatusBanner.jsx` 컴포넌트를 생성하고 `MessageList.jsx`에 추가함.
  - **Files Changed:** `app/frontend/src/components/MessageList.jsx`, `app/frontend/src/components/common/ConnectionStatusBanner.jsx`
