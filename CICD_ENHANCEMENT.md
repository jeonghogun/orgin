# CI/CD 강화 설계안

## 1. 목표

현재의 GitHub Actions 워크플로우를 확장하여, 코드 변경 시 자동으로 테스트를 실행하고, Docker 이미지를 빌드하며, 데이터베이스 마이그레이션의 정합성을 검증하는 등 CI/CD 파이프라인을 강화하는 것을 목표로 합니다. 이를 통해 코드 품질을 높이고, 배포 안정성을 확보합니다.

## 2. 현황 분석

현재 `.github/workflows/ci.yml` 워크플로우는 기본적인 린팅(linting)과 같은 정적 분석 위주로 구성되어 있을 가능성이 높습니다. 실제 코드의 동작을 검증하는 동적 테스트나, 배포 아티팩트(Docker 이미지)를 생성하는 과정이 자동화되어 있지 않습니다.

## 3. 개선 방안: GitHub Actions 워크플로우 확장

기존 `ci.yml` 워크플로우에 아래와 같은 잡(Job)들을 추가하거나 수정할 것을 제안합니다. 이 잡들은 Pull Request가 생성되거나 main 브랜치에 코드가 푸시될 때마다 실행됩니다.

### 3.1. `test` 잡: 자동화된 테스트 실행

- **목표:** Unit, Integration, E2E 테스트를 CI 환경에서 자동으로 실행하여 코드 변경으로 인한 회귀(regression)를 조기에 발견합니다.
- **구현 전략:**
    1. **서비스 컨테이너 실행:** `docker-compose.test.yml` 파일을 사용하여 `test-db`(PostgreSQL)와 `test-redis` 서비스를 CI 러너(runner) 위에 직접 실행합니다.
    2. **테스트 실행:** 모든 서비스가 healthy 상태가 되면, `scripts/run_tests.sh` 스크립트를 실행하여 전체 테스트를 수행합니다.
    3. **환경 변수:** GitHub Actions의 Secrets 기능을 사용하여 테스트에 필요한 환경 변수(`DATABASE_URL`, `REDIS_URL` 등)를 안전하게 주입합니다.

### 3.2. `build` 잡: Docker 이미지 빌드 및 푸시

- **목표:** 테스트가 성공적으로 완료된 코드에 대해 프로덕션용 Docker 이미지를 빌드하여, 언제든지 배포 가능한 상태를 유지합니다.
- **구현 전략:**
    1. **의존성:** `test` 잡이 성공적으로 완료된 후에만 실행되도록 설정합니다 (`needs: test`).
    2. **Docker 로그인:** Docker Hub나 ECR, GCR과 같은 컨테이너 레지스트리에 로그인합니다. (자격 증명은 GitHub Secrets 사용)
    3. **이미지 빌드 및 태깅:** `Dockerfile`을 사용하여 이미지를 빌드합니다. Git 태그나 커밋 해시를 사용하여 이미지에 버전 태그를 붙입니다.
    4. **이미지 푸시:** 빌드된 이미지를 컨테이너 레지스트리에 푸시합니다.

### 3.3. `migration-check` 잡: 마이그레이션 정합성 검증

- **목표:** 개발자가 ORM 모델(`orm_models.py`)을 수정하고 마이그레이션 파일 생성을 누락하는 실수를 방지합니다.
- **구현 전략:**
    1. **의존성 설치:** 애플리케이션 의존성을 설치합니다.
    2. **Alembic Check 실행:** `alembic check` 명령어를 실행합니다. 이 명령어는 현재 DB 모델과 마이그레이션 기록이 일치하는지 확인합니다.
    3. **실패 처리:** 만약 `alembic check`가 실패하면(불일치가 발견되면), CI 잡을 실패 처리하여 Pull Request가 병합되지 않도록 막습니다.

## 4. 최종 워크플로우 샘플 (`ci.yml`)

아래는 위 설계안을 바탕으로 제안하는 `.github/workflows/ci.yml`의 전체 구조입니다.

```yaml
name: CI Pipeline

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install flake8
      - name: Run linter
        run: flake8 .

  migration-check:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Check for migration consistency
        run: |
          export PYTHONPATH=$PWD
          alembic check

  test:
    runs-on: ubuntu-latest
    needs: lint
    services:
      test-db:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: test_origin_db
        ports:
          - 5434:5432
        options: >-
          --health-cmd "pg_isready -U test_user -d test_origin_db"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5
      test-redis:
        image: redis:7-alpine
        ports:
          - 6380:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      - name: Run tests
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5434/test_origin_db
          REDIS_URL: redis://localhost:6380/0
          # ... (other test env vars) ...
        run: |
          export PYTHONPATH=$PWD
          ./scripts/run_tests.sh

  build:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main' # main 브랜치에 푸시될 때만 실행
    steps:
      - uses: actions/checkout@v3
      - name: Login to Docker Hub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: your-dockerhub-repo/origin-project:latest
```
