# Origin 운영 런북

Origin 플랫폼을 운영 환경에 배포하고 유지보수할 때 따라야 할 필수 절차를 정리했습니다. CI 파이프라인, 데이터베이스, 모니터링, 사고 대응의 4가지 축으로 구성되어 있습니다.

## 1. 배포 전 점검 체크리스트
1. **DB 마이그레이션 검증**  
   ```bash
   export DATABASE_URL=postgresql://test_user:test_password@localhost:5435/test_origin_db
   export DB_ENCRYPTION_KEY=test-key-for-ci-32-bytes-long
   alembic upgrade head
   alembic check
   ```
   GitHub Actions 의 `migration-check` 잡은 위 명령을 컨테이너형 Postgres에 대해 자동으로 실행합니다.【F:.github/workflows/ci.yml†L29-L64】
2. **백엔드 테스트 실행**  
   ```bash
   ./scripts/run_tests.sh
   ```
   스크립트는 `pytest`를 호출하고 기본적으로 `DATABASE_URL`이 지정되지 않은 경우 테스트 전용 DB 주소로 대체합니다.【F:scripts/run_tests.sh†L1-L35】
3. **프론트엔드 빌드 확인**  
   ```bash
   pushd app/frontend
   npm ci
   npm run build
   popd
   ```
   빌드 산출물은 CI의 `build-frontend` 잡에서 검증되지만, 로컬 릴리즈 전 점검 시에도 동일 절차를 권장합니다.【F:.github/workflows/ci.yml†L66-L88】

## 2. 데이터베이스 & 스키마 건강 상태 유지
- **ORM 정의 동기화**: `app/models/orm_models.py`는 운영 중인 스키마의 핵심 테이블(메시지 버전, 사용자 팩트, 감사 로그, KPI 스냅샷 등)을 모두 선언합니다. 신규 마이그레이션 작성 시 반드시 이 파일을 함께 갱신해 Alembic 자동 생성이 실제 스키마와 어긋나지 않도록 합니다.【F:app/models/orm_models.py†L1-L238】
- **마이그레이션 실행 규칙**: Alembic은 애플리케이션 설정에서 `DATABASE_URL`을 읽고 동일한 연결을 사용하도록 구성되어 있습니다. 운영 DB에 적용하기 전에 staging 환경에서 `alembic upgrade head`를 적용해 의존성 확장(예: `pgvector`)이 정상 동작하는지 확인하세요.【F:alembic/env.py†L11-L55】

## 3. 모니터링 & 알림 체계
- **로컬 관측성 스택**: `docker-compose.monitoring.yml`은 Prometheus/Grafana 구성을 제공하며, API는 `/metrics` 엔드포인트로 메트릭을 노출합니다.【F:docker-compose.monitoring.yml†L1-L68】
- **대시보드 지표**: Grafana 대시보드는 RPS, 오류율, P95 지연, 메모리 사용량을 기본으로 제공합니다. 추가 패널은 `OBSERVABILITY_GUIDE.md`의 절차를 따라 커스터마이징할 수 있습니다.【F:OBSERVABILITY_GUIDE.md†L1-L40】
- **추적/로그 연동**: OpenTelemetry 수집 엔드포인트는 환경 변수(`OTEL_EXPORTER_OTLP_ENDPOINT`)로 제어되므로, 운영 환경에서는 APM 백엔드 주소를 주입해 추적 데이터를 수집하세요.【F:app/config/settings.py†L78-L118】

## 4. 사고 대응 & 상태 초기화
- **테스트 및 QA 환경 초기화**: 자동화 스크립트 `scripts/run_tests_with_clean_env.sh`는 테스트 전용 Docker Compose 스택을 기동하고 스키마를 초기화한 뒤 테스트를 실행합니다. 로컬 재현이 필요할 때 동일 스크립트로 안전하게 환경을 재구성할 수 있습니다.【F:scripts/run_tests_with_clean_env.sh†L1-L63】
- **단일 테스트 격리**: `tests/conftest.py`의 `clean_persistence_state` 픽스처가 각 테스트마다 Postgres와 Redis를 비우므로, 실패한 케이스가 다음 테스트에 영향을 주지 않습니다. 장애 재현 시에도 동일 로직을 참고하여 데이터 리셋 절차를 수행하세요.【F:tests/conftest.py†L1-L120】
- **데이터 모델 문제 대응**: 메시지 버전/요약 노트/사용자 팩트 등 신규 테이블은 ORM과 Alembic이 모두 정의하고 있으므로, 불일치가 감지되면 즉시 `orm_models.py`와 최신 마이그레이션을 비교해 누락된 열이나 제약을 보완합니다.【F:app/models/orm_models.py†L200-L238】

> **Tip:** 런북을 주기적으로 검토하여 신규 마이그레이션과 CI 단계가 추가될 때마다 본 문서를 업데이트하세요.
