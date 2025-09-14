# 테스트 환경 설계 및 실행 가이드

## 1. 개요

이 문서는 Origin 프로젝트의 전체 테스트 스위트(`unit`, `integration`, `e2e`)를 실행하기 위한 환경 설계와 단계별 가이드를 제공합니다.

현재 샌드박스 환경에서는 `pip install` 타임아웃 문제와 외부 서비스(PostgreSQL, Redis)의 부재로 인해 전체 테스트 실행이 불가능합니다. 이 문서는 로컬 개발 환경에서 Docker를 사용하여 모든 테스트를 안정적으로 실행하는 방법을 안내합니다.

## 2. 기본 테스트 실행 스크립트

- **경로:** `scripts/run_tests.sh`
- **기능:** 이 스크립트는 `pytest`를 사용하여 `tests/` 디렉토리 아래의 모든 테스트(unit, integration, e2e)를 실행하는 단일 진입점입니다.

## 3. 로컬 재현 환경 (Docker 기반)

샌드박스 또는 CI 환경의 제약으로 인해 전체 테스트 스위트 실행이 실패할 경우, 아래 가이드를 따라 로컬 Docker 환경에서 모든 테스트를 재현하고 통과시킬 수 있습니다.

### 3.1. 사전 요구사항

- Docker
- Docker Compose
- Python 3.12+
- `pip`

### 3.2. 단계별 실행 가이드

1.  **프로젝트 클론 및 이동:**
    ```bash
    git clone <repository_url>
    cd origin-project
    ```

2.  **테스트 의존성 설치:**
    ```bash
    pip install -r requirements-dev.txt
    ```

3.  **환경 변수 파일 생성:**
    프로젝트 루트에 `.env` 파일을 생성하고 아래 "환경 변수 샘플" 섹션의 내용을 복사하여 붙여넣습니다.
    ```bash
    cp .env.example .env
    # .env 파일을 열어 아래 샘플과 같이 수정합니다.
    ```

4.  **테스트 서비스 실행:**
    `docker-compose.test.yml` 파일을 사용하여 테스트에 필요한 PostgreSQL 및 Redis 컨테이너를 백그라운드에서 실행합니다.
    ```bash
    docker-compose -f docker-compose.test.yml up -d
    ```

5.  **서비스 Health Check (중요):**
    컨테이너가 완전히 실행되고 연결을 받을 준비가 될 때까지 기다립니다. 아래 명령어로 상태를 확인할 수 있습니다. `STATUS`가 `healthy`가 될 때까지 몇 초 정도 기다려야 합니다.
    ```bash
    docker-compose -f docker-compose.test.yml ps
    # NAME                STATUS
    # test-db-1           running (healthy)
    # test-redis-1        running (healthy)
    ```

6.  **전체 테스트 스위트 실행:**
    모든 서비스가 준비되면, `run_tests.sh` 스크립트를 실행합니다.
    ```bash
    # PYTHONPATH 설정이 필수적입니다.
    export PYTHONPATH=$PWD
    ./scripts/run_tests.sh
    ```

7.  **테스트 서비스 종료:**
    테스트가 완료되면 아래 명령어로 컨테이너를 종료하고 관련 볼륨을 삭제합니다.
    ```bash
    docker-compose -f docker-compose.test.yml down -v
    ```

### 3.3. 환경 변수 (`.env`) 샘플

아래 내용을 복사하여 프로젝트 루트의 `.env` 파일에 저장하십시오.

```env
# Database Configuration for Local Testing
DATABASE_URL=postgresql://test_user:test_password@localhost:5434/test_origin_db
DB_ENCRYPTION_KEY=test-encryption-key-32-bytes-long # 테스트용 32바이트 키

# Redis Configuration for Local Testing
REDIS_URL=redis://localhost:6380/0

# LLM API Keys (can be dummy values for most tests, but must be present)
OPENAI_API_KEY="sk-dummy"
GOOGLE_API_KEY="dummy"
ANTHROPIC_API_KEY="dummy"

# Auth Configuration
AUTH_OPTIONAL=True # 인증을 비활성화하여 테스트 용이성 확보

# Celery Configuration
CELERY_BROKER_URL="redis://localhost:6380/0"
CELERY_RESULT_BACKEND="redis://localhost:6380/0"
CELERY_TASK_ALWAYS_EAGER=True # 테스트 중에는 비동기 태스크를 동기적으로 실행

# Other settings
DEBUG=True
METRICS_ENABLED=False
```

## 4. 샌드박스/CI 환경에서의 제약 및 한계

- **의존성 설치 시간 초과:** `pip install -r requirements-dev.txt` 명령어가 샌드박스의 400초 시간 제한을 초과하여 실패했습니다. 이는 대량의 패키지를 설치할 때 발생하는 문제입니다.
- **외부 서비스 부재:** 테스트 스위트는 PostgreSQL(pgvector 포함) 및 Redis 서비스에 대한 연결을 필요로 합니다. 샌드박스 환경에는 이러한 서비스가 실행되고 있지 않아 통합 및 E2E 테스트가 실패할 수밖에 없습니다.
- **결론:** 위와 같은 제약으로 인해, 이 프로젝트의 신뢰성 있는 테스트는 Docker를 통해 모든 백엔드 서비스를 실행할 수 있는 로컬 환경에서 수행하는 것이 필수적입니다.
