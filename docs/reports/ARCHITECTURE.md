# Origin Project Architecture Overview

This document provides a high-level overview of the Origin project's system architecture, data flow, and key components.

## 1. System Components

The application is a containerized, multi-service system designed for scalability and reliability.

-   **Nginx Reverse Proxy**: The main entry point for all incoming traffic. It proxies all API and WebSocket traffic to the FastAPI backend.
-   **FastAPI Backend (`api`)**: The core application server. It handles all HTTP requests, serves the React frontend, manages WebSocket connections, and dispatches tasks to the Celery workers.
-   **Celery Workers**: Asynchronous task processors for the multi-agent review, persona generation, etc. Configured with a multi-queue setup for prioritization.
-   **PostgreSQL Database (`db`)**: The primary data store. It uses several key extensions:
    -   `pgvector`: For semantic similarity searches.
    -   `pgcrypto`: For field-level encryption of sensitive data, including user profiles and message content.
-   **Alembic**: The database migration tool used to manage and apply schema changes in a version-controlled manner.
-   **Redis**: Serves two critical roles:
    -   **Celery Broker & Backend**: Manages task queues.
    -   **Idempotency & Caching**: Used to store idempotency keys for API requests.

## 2. Memory & Retrieval Architecture

The system employs a two-tier memory architecture to balance retrieval accuracy with long-term efficiency.

-   **Tier 1: Recent Memory (Full-Text + Vector)**
    -   **Storage**: Raw message content and its embedding are stored in the `messages` table.
    -   **Indexing**: This tier is indexed two ways for hybrid retrieval:
        1.  A `tsvector` column for BM25-like full-text search.
        2.  A `vector` column (pgvector) for semantic similarity search.
    -   **Lifecycle**: Messages remain in this tier for a configurable period (e.g., 30 days) before being archived.

-   **Tier 2: Long-Term Memory (Summarized Facts & Notes)**
    -   **Storage**:
        -   `user_facts`: A table storing discrete, key-value facts about a user (e.g., "user's goal is X").
        -   `summary_notes`: A table storing weekly, LLM-generated summaries of conversations for each room.
    -   **Archival**: A scheduled Celery task (`archive_old_memories_task`) runs periodically to find messages that have aged out of Tier 1. It summarizes them, extracts key facts, and stores them in the Tier 2 tables. The original raw messages are then deleted to save space.

-   **Hybrid Retrieval Pipeline**:
    1.  When a query is made, the `RAGService` calls `MemoryService.get_relevant_memories_hybrid`.
    2.  This function fetches two sets of candidates in parallel: one from a BM25 full-text search and one from a pgvector cosine similarity search.
    3.  The relevance scores from both sets are normalized and combined using a weighted average (`HYBRID_BM25_WEIGHT`, `HYBRID_VEC_WEIGHT`).
    4.  The combined scores are adjusted with an exponential time decay factor, giving more weight to recent conversations.
    5.  An optional re-ranking step can be applied using a cross-encoder model to further refine the top results.
    6.  The final, ranked list of messages is returned, along with any relevant `user_facts` and `summary_notes`.
-   **Inheritance**: The retrieval process respects the `Main -> Sub` room hierarchy, querying for memories in both the current sub-room and its parent main-room.

## 3. Configuration & Secrets Management

The system's configuration is designed to be flexible and secure, separating configuration from secrets.

-   **`SecretProvider` Abstraction**: A core protocol (`app/core/secrets.py`) that decouples services from the source of secrets. The default implementation, `EnvSecrets`, reads from environment variables, but this can be replaced with providers for Vault, AWS Secrets Manager, etc., without changing service-level code.
-   **`LLMStrategyService`**: Manages the configuration of AI panelists. It loads a `config/providers.yml` file, which defines the default providers, models, personas, timeouts, and retry settings. This allows operators to change the AI panel composition without deploying new code.
-   **Dependency Injection**: All services that require secrets or configuration (e.g., `DatabaseService`, `LLMService`) receive them via FastAPI's dependency injection system, ensuring loose coupling and high testability.

## 3. Reliability & Resilience

Several patterns have been implemented to ensure system stability.

-   **Celery Task Retries**: All critical Celery tasks (e.g., `run_initial_panel_turn`) are configured with `autoretry_for=(Exception)` and exponential backoff. This allows them to automatically recover from transient failures, such as temporary network issues or LLM API errors.
-   **API Idempotency**: The review creation endpoint (`POST /api/rooms/{sub_room_id}/reviews`) supports an `Idempotency-Key` HTTP header. If a request is received with a key that has been processed within the last 24 hours, the original response is returned from a Redis cache, preventing duplicate review creation.
-   **Cost Guardrails**: The system includes two levels of cost control: a per-review token budget and a daily organization-wide token budget, both configured via environment variables. If a budget is exceeded, the review process is gracefully halted to prevent unexpected costs.

## 4. Observability

-   **Prometheus Metrics**: The application exposes a `/metrics` endpoint, instrumented with `prometheus-fastapi-instrumentator`.
-   **Custom Metrics**: In addition to default API metrics, custom metrics are exposed for key business logic:
    -   `origin_llm_calls_total{provider, outcome}`: Tracks the number of calls to each LLM provider, labeled by success or failure.
    -   `origin_llm_latency_seconds{provider}`: A histogram tracking the latency of each provider's responses.
    -   `origin_tokens_total{provider, kind}`: Tracks prompt and completion tokens used per provider.
-   **Distributed Tracing**: A unique `trace_id` is generated for each review and passed through the entire Celery task chain, included in all logs to allow for easy correlation and debugging of a single process across distributed services.

## 5. Multi-Agent Review Flow

The review process is designed to be configurable and resilient.

- **Configurability**: The AI panel is defined in `config/providers.yml`. The API for creating a review accepts an optional `panelists` array of provider names (e.g., `["openai", "claude"]`) to override the default panel for a specific review.
- **Fallback Logic**: During the initial analysis round, if a requested provider fails after multiple retries, the system automatically falls back and re-runs that panelist's turn using the default provider (the first one listed in `providers.yml`). This ensures the debate can continue with the full number of panelists.

## 6. Real-time WebSocket Flow

The real-time review status update mechanism is a key feature that demonstrates the interaction between several components.
(This section remains largely the same as before, but is now more reliable due to the Nginx fix and Celery retries).
