# 프론트엔드 UX 개선 설계안

## 1. 목표

현재 프론트엔드 애플리케이션의 사용자 경험(UX)을 개선하여, 사용자에게 보다 명확하고, 친절하며, 전문적인 인터페이스를 제공하는 것을 목표로 합니다. 주요 개선 영역은 에러 핸들링, 로딩 상태, 그리고 실시간 연결 상태 관리입니다.

## 2. 에러 핸들링: `alert()`를 Toast UI로 교체

### 2.1. 문제점
현재 `app/frontend/src/App.jsx`의 `useMutation` 에러 핸들러 등에서 시스템 `alert()`를 사용하여 오류를 표시합니다.
- **사용자 경험 저해:** `alert()`는 브라우저의 모든 동작을 차단하는 모달 대화상자로, 사용자 흐름을 강제로 중단시켜 매우 부정적인 경험을 줍니다.
- **디자인 비일관성:** 브라우저 기본 UI를 사용하므로 애플리케이션의 디자인과 일치하지 않습니다.
- **정보 전달의 한계:** 제한된 텍스트 외에 다른 정보(예: 아이콘, 재시도 버튼)를 담기 어렵습니다.

### 2.2. 개선 방안
**`react-hot-toast` 라이브러리 도입**을 제안합니다.

- **선택 이유:**
    - **경량성:** 매우 가볍고 빠릅니다.
    - **쉬운 사용법:** `<Toaster />` 컴포넌트를 앱 최상단에 추가하고, `toast.success('성공!')`, `toast.error('실패!')`와 같이 간단하게 호출할 수 있습니다.
    - **비차단적(Non-blocking):** 화면의 한쪽 구석에 잠시 나타났다가 사라지므로 사용자 작업을 방해하지 않습니다.
    - **높은 커스터마이징:** 디자인, 위치, 지속 시간 등을 쉽게 변경할 수 있습니다.

- **구현 계획:**
    1. `npm install react-hot-toast` 또는 `yarn add react-hot-toast`로 라이브러리를 설치합니다.
    2. `app/frontend/src/main.jsx`의 최상위 레벨에 `<Toaster />` 컴포넌트를 추가합니다.
    3. `app/frontend/src/App.jsx` 등에서 `alert()`를 사용하던 모든 `onError` 핸들러를 `toast.error(error.message)` 형태로 교체합니다.

## 3. 로딩 상태 개선: Skeleton UI 도입

### 3.1. 문제점
데이터를 불러오는 동안 사용자는 빈 화면이나 부분적으로 렌더링된 화면을 보게 되어, 시스템이 멈췄는지 혹은 무엇을 기다리는지 알기 어렵습니다.

### 3.2. 개선 방안
**재사용 가능한 `Skeleton` 컴포넌트 구현**을 제안합니다.

- **Skeleton UI란?** 데이터가 로드될 위치에 실제 UI와 비슷한 형태의 회색 상자를 먼저 보여주는 방식입니다. Facebook, LinkedIn 등에서 널리 사용되며, 사용자가 콘텐츠 구조를 미리 인지하게 하여 체감 로딩 속도를 줄여줍니다.

- **구현 계획:**
    1. `app/frontend/src/components/common/Skeleton.jsx` 컴포넌트를 생성합니다.
    2. CSS 애니메이션(e.g., `pulse`)을 사용하여 로딩 중임을 시각적으로 표현합니다.
    3. `useQuery`를 사용하는 컴포넌트에서 `isLoading` 상태일 때, 실제 데이터 대신 이 `Skeleton` 컴포넌트를 여러 개 렌더링하도록 수정합니다. (예: 채팅방 목록, 메시지 목록 로딩 시)

## 4. 실시간 연결 상태 관리 UX

### 4.1. 현황 및 문제점
- **백엔드:** `app/main.py`와 `app/services/redis_pubsub.py`를 통해 WebSocket 및 Redis Pub/Sub 기반의 실시간 이벤트 전송 시스템이 **구현되어 있습니다.**
- **프론트엔드:** `app/frontend/src/hooks/useWebSocket.js`에 자동 재연결 로직을 포함한 **준비된 WebSocket 훅이 존재합니다.**
- **문제점:** 코드 분석 결과, 현재 프론트엔드의 어떤 컴포넌트도 이 `useWebSocket` 훅을 **사용하고 있지 않습니다.** 즉, 백엔드의 실시간 기능이 프론트엔드에 전혀 연결되지 않아, 사용자는 리뷰 진행 상황과 같은 이벤트를 실시간으로 받지 못하고 페이지를 새로고침해야만 상태를 확인할 수 있습니다.

### 4.2. 개선 방안
**준비된 `useWebSocket` 훅을 사용하여 실시간 기능을 활성화**하는 것을 다음 단계의 최우선 과제로 제안합니다.

- **구현 계획 (제안):**
    1. **`MessageList.jsx` 수정:** 리뷰룸(`type: 'review'`)에 있을 때, `useWebSocket` 훅을 호출하여 `review_{roomId}` 채널을 구독합니다.
        ```javascript
        // In MessageList.jsx
        const { connectionStatus } = useWebSocket(
          currentRoom?.type === 'review' ? `/api/ws/reviews/${roomId}` : null,
          (message) => {
            // 새 메시지나 상태 업데이트를 react-query 캐시에 추가
            queryClient.setQueryData(['messages', roomId], (oldData) => [...oldData, message]);
          }
        );
        ```
    2. **`ConnectionStatusBanner.jsx` 컴포넌트 생성:** `connectionStatus` 값('reconnecting', 'disconnected' 등)에 따라 적절한 UI 피드백(e.g., "실시간 연결이 끊겼습니다. 재연결 중...")을 표시하는 배너 컴포넌트를 만듭니다.
    3. **UI에 배너 추가:** `Main.jsx` 또는 `App.jsx`의 최상단에 `ConnectionStatusBanner`를 추가하여 전역적으로 연결 상태를 표시합니다.

- **기대 효과:** 이 구현이 완료되면, 사용자는 더 이상 페이지를 새로고침하지 않아도 AI 리뷰 패널의 발언이 실시간으로 화면에 나타나는 것을 볼 수 있게 되어, 제품의 핵심 가치가 크게 향상됩니다.
