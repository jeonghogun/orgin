# North Star vs 현재 코드 갭 분석 및 3단계 수정안

## 현재 상황 진단

### ✅ 이미 구현된 부분
- FastAPI + Uvicorn 단일 앱 실행 가능
- `/health` 엔드포인트 정상 작동 (200 OK)
- 정적 파일 마운트 (`/static`)
- 기본 채팅 기능 (시간/검색 인텐트 포함)
- LLM 서비스 지연 초기화
- Firebase 서비스 지연 초기화
- 환경 변수 로딩 (`load_dotenv()`)

### ❌ North Star와 불일치하는 부분

#### 1. 런타임/아키텍처 문제
- **StaticFiles 마운트**: 현재 `/static`으로 마운트, North Star는 `/`로 마운트 요구
- **이벤트 드리븐 파이프라인**: 미구현 - 현재는 단순 대화만
- **라운드 기반 검토**: 미구현 - R1→R2→R3→종합 구조 없음
- **토큰 주입**: 미구현 - Authorization 헤더 자동 부착 없음

#### 2. 폴더 구조 문제
- **절대 import**: 일부 상대 import 남아있음
- **__init__.py**: 일부 폴더에 누락 가능성
- **pyproject.toml**: 중복 키/테이블 문제

#### 3. API 계약 문제
- **검토 관련 엔드포인트**: 미구현
  - `POST /api/rooms/{room_id}/reviews`
  - `GET /api/reviews/{id}`
  - `GET /api/reviews/{id}/events`
  - `GET /api/reviews/{id}/report`
- **이벤트 스키마**: 미정의
- **보고서 스키마**: 미정의

#### 4. 프론트 UX 문제
- **우측 검토 패널**: 현재는 단순 토글, North Star는 슬라이딩 대화형
- **라운드별 대화 시뮬레이션**: 미구현
- **URL 상태 관리**: 미구현 (`pushState`/`replaceState`)
- **최종 보고서 탭**: 미구현

#### 5. 품질/진단 문제
- **로그 표준화**: 미구현
- **타임아웃 가드**: 미구현
- **재시도 로직**: 미구현

## 3단계 수정안

### Phase 1: 서버/런타임 정상화 (Blocker 해결)
**목표**: North Star 아키텍처 기반 완전히 동작하는 서버

#### 1.1 StaticFiles 마운트 수정
```python
# app/main.py
app.mount("/", StaticFiles(directory="app/frontend", html=True), name="static")
```

#### 1.2 검토 관련 API 엔드포인트 구현
- `POST /api/rooms/{room_id}/reviews` - 검토 생성
- `GET /api/reviews/{id}` - 검토 상태 조회
- `GET /api/reviews/{id}/events` - 이벤트 스트림
- `GET /api/reviews/{id}/report` - 최종 보고서

#### 1.3 이벤트 스키마 정의
```python
# app/models/schemas.py
class Event(BaseModel):
    ts: int
    round: int
    actor: str
    role: str
    content: str
    meta: Optional[Dict[str, Any]] = None
```

#### 1.4 최종 보고서 스키마 정의
```python
# app/models/schemas.py
class FinalReport(BaseModel):
    executive_summary: str
    recommendation: Literal["adopt", "trial", "hold", "drop"]
    round_summaries: List[str] = []
    sources: List[str] = []
    proposals: List[str] = []
```

### Phase 2: 이벤트→대화 메시지 변환
**목표**: 검토 파이프라인을 대화형으로 구현

#### 2.1 이벤트 드리븐 검토 서비스 구현
```python
# app/services/review_service.py
class ReviewService:
    async def create_review(self, room_id: str, topic: str) -> str
    async def generate_round_1(self, review_id: str) -> List[Event]
    async def generate_round_2(self, review_id: str) -> List[Event]
    async def generate_round_3(self, review_id: str) -> List[Event]
    async def generate_final_report(self, review_id: str) -> FinalReport
```

#### 2.2 이벤트 스트림 API 구현
```python
# app/main.py
@app.get("/api/reviews/{review_id}/events")
async def get_review_events(
    review_id: str,
    since: int = 0
) -> List[Event]
```

#### 2.3 프론트엔드 대화형 UI 구현
- 우측 패널을 슬라이딩 대화형으로 변경
- 이벤트를 실시간 대화 메시지로 변환
- 라운드별 순차 발화 시뮬레이션

### Phase 3: URL/패널 동작 및 품질 보장
**목표**: 완전한 UX 및 안정성 확보

#### 3.1 URL 상태 관리
```javascript
// 검토 시작 시
history.pushState({review_id: id}, '', `?review_id=${id}`);

// 패널 닫기 시
history.replaceState(null, '', '/');
```

#### 3.2 토큰 주입 시스템
```javascript
// 모든 fetch에 자동 Authorization 헤더 부착
const token = localStorage.getItem('idToken');
if (token) {
    headers['Authorization'] = `Bearer ${token}`;
}
```

#### 3.3 로그 표준화 및 타임아웃 가드
```python
# 표준화된 로그 포맷
logger.info("final_report_written", extra={
    "id": review_id,
    "size": len(report_content)
})
```

#### 3.4 재시도 로직 구현
```python
# 지수 백오프 재시도
async def retry_with_backoff(func, max_retries=5):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
```

## 현재 코드와 North Star 간 주요 갭

### 1. 아키텍처 갭
- **현재**: 단순 대화 시스템
- **North Star**: 이벤트 드리븐 검토 파이프라인

### 2. API 갭
- **현재**: `/api/rooms/{id}/messages` (단순 대화)
- **North Star**: `/api/reviews/{id}/events` (이벤트 스트림)

### 3. UX 갭
- **현재**: 좌측 채팅 + 우측 토글 패널
- **North Star**: 좌측 대화 + 우측 슬라이딩 대화형 검토

### 4. 데이터 모델 갭
- **현재**: Message 스키마만 존재
- **North Star**: Event, FinalReport, Review 스키마 필요

### 5. 상태 관리 갭
- **현재**: 로컬 상태만
- **North Star**: URL 기반 상태 복원 + 이벤트 스트림

## 다음 단계 우선순위

1. **Phase 1 완료**: 검토 API 및 스키마 구현
2. **Phase 2 완료**: 이벤트 드리븐 파이프라인 구현
3. **Phase 3 완료**: UX 완성 및 안정성 확보

각 Phase는 독립적으로 테스트 가능하며, Phase 1 완료 후 서버는 North Star 아키텍처를 완전히 지원하게 됩니다.
