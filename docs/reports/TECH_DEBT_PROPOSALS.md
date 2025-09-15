# 기술 부채 제안서 (Technical Debt Proposals)

이 문서는 현재 코드베이스에서 발견된 장기적인 기술 부채와 이를 해결하기 위한 제안을 담고 있습니다. 이 제안들은 당장의 긴급한 수정 사항은 아니지만, 프로젝트의 장기적인 확장성과 유지보수성을 위해 고려되어야 합니다.

## 1. ORM/마이그레이션 관리 방침

**현황:**
현재 `app/models/orm_models.py`와 실제 DB 스키마가 동기화되었고, 마이그레이션 스크립트가 SQLite와 호환되도록 수정되었습니다. 이는 큰 진전이지만, 향후 불일치가 다시 발생하지 않도록 명확한 정책이 필요합니다.

**제안:**
1.  **ORM 우선 원칙 (ORM-First Principle):** 모든 데이터베이스 스키마 변경은 반드시 `app/models/orm_models.py`의 SQLAlchemy 모델을 먼저 수정하는 것으로 시작해야 합니다.
2.  **자동 생성 활용:** 스키마 변경 후, `alembic revision --autogenerate -m "설명"` 명령어를 사용하여 마이그레이션 스크립트의 초안을 생성합니다.
3.  **수동 검토 및 수정:** 자동 생성된 스크립트를 개발자가 직접 검토하고, `batch_alter_table`과 같은 호환성 로직이나 데이터 마이그레이션 구문을 필요에 따라 추가합니다. 원시 SQL (`op.execute`) 사용은 최소화하고 불가피할 경우에만 사용합니다.
4.  **로컬 검증 필수:** 모든 마이그레이션 스크립트는 `alembic upgrade head`와 `alembic downgrade base` 명령어를 통해 로컬 PostgreSQL 및 SQLite 환경 양쪽에서 검증된 후에만 병합되어야 합니다.

## 2. 관측 가능성(Observability) 스택 단일화 방안

**현황:**
`app/config/settings.py`에 New Relic과 Datadog 설정이 모두 존재하며, `app/main.py`에는 Prometheus가 구현되어 있습니다. 여러 APM 도구를 동시에 사용하는 것은 설정이 복잡해지고, 데이터가 분산되며, 비용이 증가하는 문제가 있습니다.

**제안 (주력 1개 제안):**
**Datadog를 주력 관측 가능성 도구로 단일화**할 것을 제안합니다.

-   **로그 (Logging):** 현재의 `logging` 설정을 유지하되, Datadog Agent를 통해 로그를 수집하여 Datadog Logs로 전송합니다. JSON 포맷터(e.g., `python-json-logger`)를 도입하면 파싱이 용이해집니다.
-   **메트릭 (Metrics):** `prometheus-fastapi-instrumentator`를 `ddtrace-py`의 FastAPI 통합으로 교체합니다. `ddtrace`는 API 메트릭뿐만 아니라, `psycopg2`, `redis`, `celery` 등 주요 라이브러리의 성능 메트릭을 자동으로 계측하여 더 풍부한 데이터를 제공합니다.
-   **APM (Application Performance Monitoring):** `ddtrace-py`가 분산 추적(Distributed Tracing)을 완벽하게 지원합니다. 현재 수동으로 생성하는 `X-Trace-ID`를 Datadog의 추적 ID와 통합하여 FastAPI, Celery, LLM 호출에 이르는 전체 요청 흐름을 시각적으로 한 번에 파악할 수 있습니다.

**기대 효과:**
로그, 메트릭, 트레이스를 Datadog라는 단일 플랫폼에서 유기적으로 연계하여 분석할 수 있게 되어, 문제 발생 시 원인 파악(Root Cause Analysis) 시간이 획기적으로 단축됩니다.

## 3. 프롬프트 외부화 운영 가이드

**현황:**
`app/tasks/review_tasks.py`에 하드코딩되어 있던 프롬프트들이 `app/prompts/` 디렉토리의 텍스트 파일로 분리되었고, `prompt_service`를 통해 로드됩니다.

**운영 가이드 제안:**
1.  **프롬프트 수정:** AI의 응답을 변경하거나 개선하고 싶을 때, 더 이상 Python 코드를 수정할 필요 없이 `app/prompts/` 디렉토리의 해당 `.txt` 파일 내용만 수정하면 됩니다.
2.  **템플릿 변수:** 프롬프트 내 `{변수명}` 형태의 플레이스홀더는 `prompt_service.get_prompt()` 호출 시 키워드 인자로 전달되는 동적 값으로 채워집니다. 새로운 변수를 추가할 경우, 프롬프트 파일과 `review_tasks.py`의 `get_prompt` 호출부를 함께 수정해야 합니다.
3.  **A/B 테스팅:** 새로운 버전의 프롬프트를 테스트하고 싶을 경우, `review_initial_analysis_v2.txt`와 같이 새 파일을 만들고 `review_tasks.py`에서 로드할 파일명만 변경하여 쉽게 실험할 수 있습니다.
4.  **버전 관리:** 모든 프롬프트 파일은 Git을 통해 버전 관리되므로, 변경 이력을 추적하고 언제든지 이전 버전으로 롤백할 수 있습니다.
