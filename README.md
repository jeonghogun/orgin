# Origin Project v2.0.0

AI 기반 다중 라운드 검토 및 분석 플랫폼

## 🚀 주요 개선사항 (v2.0.0)

### 🌟 신규 기능: AI 다중 에이전트 검토 시스템
- **Main/Sub/Review 룸 계층 구조**: 사용자의 메인 룸 아래에 프로젝트별 서브 룸을, 서브 룸 아래에 특정 주제에 대한 검토 룸을 생성하여 체계적인 컨텍스트 관리.
- **3-라운드 AI 토론**: 3개의 다른 AI 제공자(GPT, Gemini, Claude)가 독립적으로 의견을 제시(1라운드)하고, 서로의 의견을 비평하며 자신의 관점을 발전시킨 후(2라운드), 최종 결론을 도출(3라운드)하는 심층 분석 프로세스.
  - **API 기반 패널 설정**: 리뷰 생성 시 원하는 AI 패널리스트를 동적으로 선택할 수 있습니다. (e.g., `panelists: ["openai", "claude"]`)
  - **장애 극복**: 특정 AI 제공자가 응답에 실패할 경우, 기본 제공자(OpenAI)가 역할을 대신하여 토론을 계속 진행합니다.
- **자동화된 최종 보고서**: 3명의 AI가 도출한 최종 결론을 종합하여 실행 가능한 최종 보고서를 자동으로 생성하고 내보내기.

### 🧠 AI 지능화 (Phase 4-6.5)
- **LLM 기반 의도 감지**: 자연어로 사용자 의도를 정확히 파악
- **맥락 메모리 시스템**: 대화의 연속성을 보장하는 지능적 메모리
- **RAG 통합 응답**: 외부 정보를 활용한 정확하고 최신의 답변
- **Context-Aware 검색**: 이전 대화 맥락을 고려한 지능적 검색

### 📁 프로젝트 구조 개선
- **모듈화된 아키텍처**: 백엔드와 프론트엔드를 명확히 분리
- **서비스 지향 설계**: 각 기능별로 독립적인 서비스 모듈 (`review_service` 추가)
- **API 종속성 관리**: `app/api/dependencies.py`를 통해 API 종속성을 중앙에서 관리
- **테스트 디렉토리 통합**: `tests/`로 테스트 구조를 일원화하여 명확성 증진

### 🔧 기술적 개선
- **Frontend**: Vanilla JS → React (Vite)로 전환하여 컴포넌트 기반 아키텍처 구현
- **Backend**: FastAPI, Python 3.12+
- **Database**: PostgreSQL with pgvector (semantic search) and pgcrypto (field encryption)
- **Async & Messaging**: Celery (multi-queue), Redis (broker/cache), WebSockets (real-time updates)
- **Deployment**: Docker, Docker Compose, Nginx (reverse proxy), with Kubernetes manifests
- **CI/CD**: GitHub Actions for automated linting, testing, and builds

## 📋 기능

### 🤖 AI 다중 라운드 검토
- **3-라운드 심층 분석 (토큰 최적화)**:
  - **1라운드 (독립 분석)**: 3개의 AI(GPT, Gemini, Claude)가 주제에 대해 독립적으로 의견 제시.
  - **2라운드 (반박 및 개선)**: 각 AI는 자신의 1라운드 의견(전체 텍스트)과 **경쟁 AI들의 1라운드 의견 요약본**을 받습니다. 이를 통해 자신의 관점을 비평하고 개선합니다. (토큰 사용량 절약을 위해 요약본을 사용합니다.)
  - **3라운드 (최종 종합)**: 각 AI는 자신의 1, 2라운드 의견(전체 텍스트)과 **경쟁 AI들의 2라운드 의견 요약본**을 받아 최종 결론을 작성합니다.
- **실시간 대화**: AI들이 실제로 토론하는 것처럼 표시 (이벤트 기반 API 제공).
- **최종 종합 보고서**: 3개의 최종 결론을 종합하여 실행 가능한 보고서 자동 생성 및 내보내기.

### 💬 지능형 대화 시스템
- **계층적 룸 구조**: Main Room → Sub Room → Review Room으로 컨텍스트가 상속되는 구조.
- **맥락 인식 대화**: 이전 대화를 기억하고 연속성 보장
- **개인화된 응답**: 사용자 이름과 선호도를 고려한 맞춤형 응답
- **의도 기반 분기**: 시간, 날씨, 검색, 위키 등 다양한 기능 자동 분기

### 🔍 지능형 검색 및 정보 통합
- **Context-Aware 검색**: 이전 대화 맥락을 고려한 지능적 검색
- **Google Custom Search**: 실시간 웹 검색 결과
- **Wikipedia API**: 신뢰할 수 있는 참고 자료
- **정보 요약**: 검색 결과를 자연스럽게 요약하여 제공
- **출처 명시**: 정보의 출처를 명확히 표시

### 📤 데이터 내보내기
- **Markdown 형식**: 구조화된 보고서 생성
- **한국어 최적화**: 모든 텍스트 한국어로 표시
- **라운드별 요약**: 각 라운드의 핵심 내용 포함

### 🔐 인증 시스템
- **Firebase Authentication**: Google 로그인 지원
- **토큰 기반 인증**: JWT 토큰을 통한 보안
- **선택적 인증**: 개발 모드에서 인증 생략 가능

## 🏗️ 프로젝트 구조

```
app/
├── api/                   # API 라우터
│   ├── dependencies.py    # 공통 API 종속성
│   └── routes/
├── config/                # 설정 관리
│   └── settings.py
├── models/                # 데이터 모델
│   ├── schemas.py
│   └── memory_schemas.py
├── services/              # 비즈니스 로직
│   ├── llm_service.py
│   ├── review_service.py  # 신규 리뷰 서비스
│   ├── storage_service.py
│   └── ...
├── utils/                 # 유틸리티
│   └── helpers.py
├── frontend/              # 프론트엔드
│   └── ...
└── main.py                # FastAPI 애플리케이션
tests/                     # 통합 테스트 디렉토리
├── unit/                  # 단위 테스트
└── integration/           # 통합 테스트
```

## 📚 문서

### 📖 상세 문서
- **[개발자 온보딩 가이드](./DEVELOPER_ONBOARDING.md)**: 새로운 개발자를 위한 빠른 시작 가이드
- **[Phase 1-6.5 통합 보고서](./PHASE_1_6_5_INTEGRATION_REPORT.md)**: 모든 Phase별 구현 내용과 기술적 세부사항 (리팩토링 요약 및 North Star 분석 포함)

## 🚀 설치 및 실행

### 1. 환경 설정
```bash
# 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

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
```

### 3. 애플리케이션 실행
```bash
# 개발 모드 실행 (PYTHONPATH 설정 필수)
export PYTHONPATH=$PWD
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. 브라우저 접속
```
http://127.0.0.1:8000
```

### 5. API 문서
```
http://127.0.0.1:8000/docs  # Swagger UI
http://127.0.0.1:8000/redoc # ReDoc
```

## 🔧 설정 옵션

### 환경 변수
| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 키 | 필수 |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Firebase 서비스 계정 파일 경로 | 선택 |
| `GOOGLE_API_KEY` | Google API 키 | 선택 |
| `GOOGLE_CSE_ID` | Google Custom Search Engine ID | 선택 |
| `AUTH_OPTIONAL` | 인증 생략 여부 (개발용) | False |
| `API_HOST` | API 서버 호스트 | 127.0.0.1 |
| `API_PORT` | API 서버 포트 | 8000 |
| `DEBUG` | 디버그 모드 | True |

### 저장소 옵션
- **파일 시스템**: 기본 저장 방식 (개발용)
- **Firebase Firestore**: 프로덕션용 클라우드 저장소

## 📖 사용법

### 1. 지능형 대화
- 메인 채팅창에 자연어로 메시지 입력
- AI가 의도를 파악하고 맥락을 고려한 응답 생성

### 2. 검토 시작
- Sub Room에서 검토 시작 API 호출
- 예: `POST /api/rooms/{sub_room_id}/reviews`
- Body: `{ "topic": "AI의 미래", "instruction": "장단점을 분석해줘" }`

### 3. 검토 과정 관찰
- `POST /api/reviews/{review_id}/generate`를 호출하여 리뷰 프로세스 시작
- `GET /api/reviews/{review_id}/events`를 폴링하여 라운드별 AI 패널 발언 실시간 확인
- 최종 종합 보고서 자동 생성

### 4. 결과 내보내기
- `GET /api/reviews/{review_id}/report`로 최종 보고서 확인
- "내보내기" 버튼 클릭
- Markdown 형식으로 다운로드

## 🧪 테스트

### 전체 테스트 실행
```bash
# PYTHONPATH 설정이 필수적입니다.
export PYTHONPATH=$PWD
pytest tests/
```

### 단위 테스트
```bash
export PYTHONPATH=$PWD
pytest tests/unit/
```

### 통합 테스트
```bash
export PYTHONPATH=$PWD
pytest tests/integration/
```

## 📊 성능 최적화

### 백엔드
- **비동기 처리**: FastAPI의 비동기 특성 활용
- **압축**: GZip 미들웨어로 응답 압축
- **속도 제한**: API 요청 속도 제한

### 프론트엔드
- **컴포넌트 지연 로딩**: 필요시에만 컴포넌트 로드
- **이벤트 폴링 최적화**: 효율적인 실시간 업데이트
- **메모리 관리**: 불필요한 이벤트 리스너 정리

## 🔒 보안

### 인증
- Firebase Authentication을 통한 안전한 로그인
- JWT 토큰 기반 세션 관리
- API 엔드포인트 보호

### 데이터 보안
- 입력 데이터 검증 (Pydantic)
- SQL 인젝션 방지
- XSS 공격 방지

## 🤝 기여하기

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 지원

문제가 발생하거나 질문이 있으시면:
- GitHub Issues에 등록
- 이메일로 문의

---

**Origin Project v2.0.0** - AI 기반 지능형 검토 플랫폼