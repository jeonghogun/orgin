# Origin Project v2.0.0

AI 기반 다중 라운드 검토 및 분석 플랫폼

## 🚀 주요 개선사항 (v2.0.0)

### 📁 프로젝트 구조 개선
- **모듈화된 아키텍처**: 백엔드와 프론트엔드를 명확히 분리
- **서비스 지향 설계**: 각 기능별로 독립적인 서비스 모듈
- **일관된 네이밍**: 변수, 함수, 컴포넌트 이름 통일
- **중복 코드 제거**: 공통 로직을 유틸리티로 통합

### 🔧 기술적 개선
- **통합 설정 관리**: 모든 환경 변수를 중앙화된 설정으로 관리
- **데이터 모델 통합**: Pydantic 스키마를 통한 일관된 데이터 검증
- **저장소 추상화**: 파일 시스템과 Firebase를 통합 인터페이스로 관리
- **LLM 서비스 통합**: 다양한 AI 제공자를 통합된 인터페이스로 관리

### 🎨 UI/UX 개선
- **컴포넌트 기반 프론트엔드**: 재사용 가능한 JavaScript 컴포넌트
- **모듈화된 CSS**: 기능별로 분리된 스타일시트
- **반응형 디자인**: 모바일 친화적인 레이아웃
- **실시간 채팅 UI**: AI 간 대화를 자연스럽게 표시

## 📋 기능

### 🤖 AI 다중 라운드 검토
- **라운드별 분석**: Critic → Optimist → Synthesizer 순서로 진행
- **실시간 대화**: AI들이 실제로 토론하는 것처럼 표시
- **최종 종합 보고서**: Consolidator가 모든 의견을 종합

### 💬 실시간 채팅
- **메인 채팅방**: 일반 대화 및 검토 요청
- **검토 채팅방**: AI 패널들의 대화를 실시간으로 표시
- **자동 스크롤**: 새로운 메시지 자동 스크롤

### 🔍 외부 검색 통합
- **Google Custom Search**: 실시간 웹 검색 결과
- **Wikipedia API**: 신뢰할 수 있는 참고 자료
- **자동 검색**: AI 응답 시 관련 정보 자동 검색

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
├── config/                 # 설정 관리
│   └── settings.py        # 환경 변수 및 설정
├── models/                # 데이터 모델
│   └── schemas.py         # Pydantic 스키마
├── services/              # 비즈니스 로직
│   ├── llm_service.py     # LLM 통합 서비스
│   ├── storage_service.py # 데이터 저장소
│   ├── firebase_service.py # Firebase 연동
│   └── external_api_service.py # 외부 API
├── utils/                 # 유틸리티
│   └── helpers.py         # 공통 헬퍼 함수
├── frontend/              # 프론트엔드
│   ├── components/        # JavaScript 컴포넌트
│   │   ├── auth.js        # 인증 컴포넌트
│   │   ├── chat.js        # 채팅 컴포넌트
│   │   └── review-panel.js # 리뷰 패널 컴포넌트
│   ├── styles/            # CSS 스타일
│   │   └── main.css       # 메인 스타일시트
│   └── index.html         # 메인 HTML
├── tests/                 # 테스트
│   ├── unit/              # 단위 테스트
│   └── integration/       # 통합 테스트
├── docs/                  # 문서
└── main.py               # FastAPI 애플리케이션
```

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
FIREBASE_SERVICE_ACCOUNT_PATH=path/to/firebase-key.json
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CSE_ID=your_custom_search_engine_id
```

### 3. 애플리케이션 실행
```bash
# 개발 모드 실행
python app/main.py

# 또는 uvicorn 직접 실행
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. 브라우저 접속
```
http://127.0.0.1:8000
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

### 1. 일반 대화
- 메인 채팅창에 메시지 입력
- AI가 즉시 응답 생성

### 2. 검토 시작
- 메시지에 "검토", "리뷰", "토론" 포함
- 예: "AI의 미래에 대해 검토해주세요"
- 우측 패널에 검토 채팅방 자동 열림

### 3. 검토 과정 관찰
- 라운드별로 AI 패널들이 순차적으로 발언
- 각 AI의 의견을 실시간으로 확인
- 최종 종합 보고서 자동 생성

### 4. 결과 내보내기
- 검토 완료 후 "내보내기" 버튼 클릭
- Markdown 형식으로 다운로드

## 🧪 테스트

### 단위 테스트
```bash
pytest app/tests/unit/
```

### 통합 테스트
```bash
pytest app/tests/integration/
```

### 전체 테스트
```bash
pytest app/tests/
```

## 📊 성능 최적화

### 백엔드
- **비동기 처리**: FastAPI의 비동기 특성 활용
- **캐싱**: Redis를 통한 응답 캐싱
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