# 관측 가능성(Observability) 스택 설계안

## 1. 목표

이 문서는 Origin 프로젝트의 로그, 메트릭, 트레이스를 통합적으로 수집하고 분석하기 위한 관측 가능성 스택을 설계하고, 최적의 기술 스택을 제안하는 것을 목표로 합니다.

## 2. 현황 분석

현재 프로젝트는 여러 관측 가능성 도구가 혼재되어 있습니다.
- **메트릭:** `prometheus-fastapi-instrumentator`를 통해 Prometheus 형식의 메트릭을 노출하고 있습니다. (`app/main.py`)
- **설정 파일:** `app/config/settings.py`에는 New Relic과 Datadog 관련 설정 변수들이 존재합니다.
- **로그:** Python의 기본 `logging` 모듈을 사용하고 있습니다.
- **트레이싱:** `X-Trace-ID`를 수동으로 생성하고 전파하고 있습니다.

이러한 분산된 접근 방식은 데이터 사일로를 만들고, 문제 발생 시 여러 시스템을 오가며 원인을 파악해야 하는 비효율을 초래합니다.

## 3. 기술 스택 비교 및 평가

세 가지 주요 스택을 비교하여 장단점을 평가합니다.

| 항목 | 1. PLG 스택 (Prometheus + Loki + Grafana) | 2. ELK 스택 (Elasticsearch + Logstash + Kibana) | 3. OpenTelemetry + Backend |
| --- | --- | --- | --- |
| **핵심 영역** | 메트릭 및 시계열 데이터 | 로그 수집 및 검색 | **통합 (로그, 메트릭, 트레이스)** |
| **장점** | - 현재 Prometheus를 사용 중이라 확장 용이<br>- 오픈소스 생태계 활성화<br>- 비용 효율적 | - 강력한 전문 검색 및 집계 기능<br>- 대용량 로그 처리에 특화 | - **단일 표준, 단일 계측**: 코드 변경 없이 백엔드 교체 가능 (Vendor-Neutral)<br>- **자동 계측**: FastAPI, Celery, DB 등 주요 라이브러리 자동 추적<br>- **분산 추적 네이티브 지원** |
| **단점** | - 로그와 트레이스 연동이 상대적으로 약함<br>- Loki의 검색 기능이 ELK보다 제한적 | - 리소스 사용량(메모리, 디스크)이 높음<br>- 트레이스와 메트릭 지원이 부가적 | - 직접 수집기(Collector)를 운영해야 하는 복잡성 존재<br>- 아직 빠르게 발전 중인 표준 |
| **평가** | 현재 구조에서 가장 쉽게 확장할 수 있지만, 분산 추적이라는 핵심 요구사항을 해결하기 어렵습니다. | 로그 분석에는 강력하지만, APM(트레이스) 관점에서는 부족합니다. | **가장 현대적이고 포괄적인 접근 방식.** 애플리케이션의 복잡성을 고려할 때, 모든 신호를 통합 관리할 수 있는 OpenTelemetry가 가장 적합합니다. |

## 4. 최종 권장안: OpenTelemetry

**OpenTelemetry**를 프로젝트의 표준 관측 가능성 프레임워크로 도입할 것을 강력히 권장합니다.

### 4.1. 선택 근거

1.  **통합된 컨텍스트:** OpenTelemetry는 로그, 메트릭, 트레이스를 동일한 컨텍스트(Trace ID, Span ID)로 묶어줍니다. 이를 통해 "API 요청이 느려진 원인이 특정 DB 쿼리 때문"이라는 사실을 클릭 몇 번으로 드릴다운하여 찾아낼 수 있습니다.
2.  **미래 확장성 및 유연성:** 오늘은 오픈소스인 Jaeger(트레이스)와 Prometheus(메트릭)를 사용하다가도, 내일 비즈니스 요구에 따라 Datadog이나 New Relic 같은 상용 솔루션으로 코드 변경 없이 전환할 수 있습니다. 벤더 종속성에서 자유로워집니다.
3.  **풍부한 자동 계측:** FastAPI, Celery, Psycopg2(PostgreSQL), Redis 등 현재 프로젝트에서 사용하는 대부분의 라이브러리를 몇 줄의 설정만으로 자동 계측하여, 개발자가 비즈니스 로직에만 집중할 수 있게 해줍니다.

### 4.2. 아키텍처 제안

```
[FastAPI App / Celery Worker] --(OTLP)--> [OpenTelemetry Collector] --+--> [Jaeger (Traces)]
      (Auto-instrumented)                                           |--> [Prometheus (Metrics)]
                                                                    +--> [Loki (Logs)]
```

- **애플리케이션:** `opentelemetry-instrument`를 사용하여 코드를 거의 수정하지 않고 자동 계측합니다.
- **OTel Collector:** 애플리케이션으로부터 데이터를 OTLP(OpenTelemetry Protocol) 형식으로 수신하여, 각 데이터 유형에 맞는 백엔드(Jaeger, Prometheus 등)로 내보내는 역할을 하는 경량 에이전트입니다.
- **백엔드:**
    - **Traces:** Jaeger 또는 Zipkin
    - **Metrics:** Prometheus
    - **Logs:** Loki 또는 Fluentd

## 5. 최소 샘플 구현 계획

다음 단계로, 이 설계안을 바탕으로 최소한의 샘플 코드를 구현할 것입니다.
1.  `requirements-dev.txt`에 OpenTelemetry 관련 라이브러리를 추가합니다.
2.  `opentelemetry-instrument`를 사용하여 FastAPI 애플리케이션을 실행하고, 모든 API 요청이 자동으로 추적되도록 구성합니다.
3.  콘솔(Console) Exporter를 사용하여 수집된 트레이스와 로그, 메트릭이 터미널에 출력되는 것을 보여줌으로써, 계측이 성공적으로 이루어졌음을 증명합니다.
