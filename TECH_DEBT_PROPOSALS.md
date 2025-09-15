# Technical Debt & Architectural Improvement Proposals

**Status:** All major technical debt items identified during the Q3 2025 audit have been **resolved**.

This document is being kept for historical purposes and to list any minor, lower-priority items for future consideration.

---

## Resolved Technical Debt (Completed in Phase 3.5)

1.  **Refactor Initial Database Migration:**
    -   **Status:** **RESOLVED**
    -   **Action Taken:** The initial migration (`37ecae34152b...`) was completely rewritten to use dialect-agnostic Alembic `op` commands, making the full migration history compatible with SQLite.

2.  **Consolidate Review Creation Logic:**
    -   **Status:** **RESOLVED**
    -   **Action Taken:** The business logic for creating reviews was centralized into the `ReviewService`, and the API endpoint in `rooms.py` was refactored to be a thin wrapper.

3.  **Refactor Frontend State Management:**
    -   **Status:** **RESOLVED**
    -   **Action Taken:** The state management in `ChatInput.jsx` was refactored into a `useChatInputState` hook using a `useReducer` pattern, greatly improving its maintainability.

## Future Considerations (Minor / Low Priority)

1.  **Consolidate WebSocket/SSE Logic:**
    -   **Area:** `useEventSource.js`, `useWebSocket.js`, and the API routes for chat and reviews.
    -   **Observation:** The application uses two different real-time patterns: Server-Sent Events (SSE) for review updates and a direct `fetch` stream for chat responses. There is also a `useWebSocket` hook that appears to be unused.
    -   **Proposal:** For consistency, standardize on a single real-time communication strategy. SSE is often simpler for server-to-client data pushes. Refactoring the chat streaming to also use SSE could simplify the frontend hooks and backend logic. This is a low-priority architectural improvement.

2.  **Component-Scoped API Calls:**
    -   **Area:** `App.jsx` and various child components.
    -   **Observation:** Many of the React Query mutations are defined in the top-level `App.jsx` and then passed down through multiple layers of props (e.g., `createRoomMutation`).
    -   **Proposal:** Refactor this so that components that trigger a mutation also define the `useMutation` hook themselves. This improves component encapsulation and makes it easier to understand a component's dependencies and side-effects without tracing props up the tree. This is a common refactoring pattern for maturing React applications.
