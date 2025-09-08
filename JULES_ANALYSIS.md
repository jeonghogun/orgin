# Jules's Project Analysis

This document contains the Feature Matrix and Conflict/Duplication Map created as part of the initial analysis phase.

## 1. Feature Matrix

| Feature | Requirement | Implementation Status | Related Files/Endpoints | Notes |
|---|---|---|---|---|
| RAG Hybrid Search | BM25 + Vector, weighted sum, time decay | **Partial/Incorrect** | `app/services/rag_service.py`, `app/api/routes/search.py`, `app/api/routes/conversations.py` | Hybrid search exists for attachments only. Messages use Postgres FTS. No weighted sum between messages and attachments. No time decay. Endpoint is duplicated and needs to be consolidated to `/api/convo/search`. |
| Message Versioning & Diff | Backend API, Frontend Modal | **Partial** | `app/api/routes/conversations.py` (`/versions`, `/diff`), `app/frontend/src/components/DiffViewModal.jsx` | Backend APIs exist but need verification. Frontend component exists but needs to be connected to the API. |
| Cmd+K Search Panel | Real API integration, debouncing | **Not Implemented** | `app/frontend/src/components/CmdK.jsx` (assumption) | Currently uses mock data. Needs to be connected to the new `/api/convo/search`. |
| Async Export UI | Job-based polling, download link | **Partial** | `app/api/routes/exports.py`, `app/tasks/export_tasks.py`, `app/api/routes/conversations.py` | Async backend (`exports.py`, `export_tasks.py`) seems to exist. A synchronous endpoint also exists in `conversations.py`. Frontend needs to be implemented to use the async version. |
| SSE Stabilization | Heartbeat, backoff, done/error events | **Partial** | `app/api/routes/conversations.py` (`stream_message`), Frontend EventSource logic | Backend sends `delta` and `usage`, but not `done` or `error`. No heartbeat. Frontend needs exponential backoff. Cancel endpoint exists. |
| Budget/Cost Visualization | Redis cap, `BudgetDisplay.jsx` | **Partial** | `app/api/dependencies.py` (`check_budget`), `app/frontend/src/components/BudgetDisplay.jsx` (assumption) | Backend budget check exists. Frontend component needs to be implemented to show usage and warnings. |
| Monitoring | Prometheus metrics, dashboard | **Not Implemented** | `app/core/metrics.py` | Some basic metrics exist (`SSE_SESSIONS_ACTIVE`), but the required ones (`llm_requests_total`, etc.) are missing. |
| Advanced UX | Dark Theme, Hotkeys, Copy button, LaTeX | **Partial** | `app/frontend/` | Dark theme is inconsistent. Other features are not implemented. |
| Runtime: Streaming Error | Fix parsing errors | **Not Fixed** | `app/api/routes/conversations.py`, Frontend SSE handler | Likely caused by missing `done`/`error` events from the backend. |
| Runtime: Memory Failure | AI forgets last message | **Not Fixed** | `app/services/conversation_service.py`, `app/services/memory_service.py` | Suspect issue in `get_messages_by_thread` or how context is assembled for the LLM call. |

## 2. Conflict/Duplication Map

| Type | Item | Location(s) | Issue | Proposed Solution |
|---|---|---|---|---|
| **API Endpoint** | `search_conversations` | 1. `app/api/routes/search.py` (`/api/search/conversations`) <br> 2. `app/api/routes/conversations.py` (`/api/convo/search`) | Two different implementations of conversation search exist at two different endpoints, causing confusion and code duplication. SQL logic is slightly different. | Consolidate all logic into a single, correct implementation at `/api/convo/search` inside `app/api/routes/conversations.py`. Delete the endpoint from `app/api/routes/search.py`. |
| **API Endpoint** | `export_thread` | `app/api/routes/conversations.py` | A synchronous export endpoint exists, which conflicts with the requirement for an asynchronous, job-based export system. | Deprecate or remove the synchronous endpoint. Ensure all frontend interactions use the async export API in `app/api/routes/exports.py`. |
| **Search Logic** | Message Search | `app/api/routes/search.py` & `conversations.py` | Uses PostgreSQL FTS (`ts_rank`). | Requirement is to use `rank-bm25`. This logic needs to be rewritten. |
| **Search Logic** | Result Combination | `app/api/routes/search.py` & `conversations.py` | Message and attachment search results are simply concatenated and sorted. Attachment results have a placeholder score. | Implement proper weighted scoring and normalization for the combined results, including time decay. |
