# Origin Project Architecture Overview

This document provides a high-level overview of the Origin project's system architecture, data flow, and key components.

## 1. System Components

The application is a containerized, multi-service system designed for scalability and reliability.

![System Diagram](https://i.imgur.com/your-diagram-url.png)  <!-- Placeholder for a diagram -->

-   **Nginx Reverse Proxy**: The main entry point for all incoming traffic. It serves the static frontend assets and acts as a reverse proxy for all API and WebSocket traffic, directing it to the FastAPI backend.

-   **FastAPI Backend (`api`)**: The core application server. It handles all HTTP requests, serves the React frontend, manages WebSocket connections, and dispatches tasks to the Celery workers. It is a stateless service that can be horizontally scaled.

-   **Celery Workers**: Asynchronous task processors that handle the multi-agent review process. They are configured with a multi-queue setup. The core task logic in `review_tasks.py` has been refactored into smaller, more maintainable functions to improve clarity and testability.
    -   `worker-high-priority`: Handles the initial, user-facing turn of the debate.
    -   `worker-default`: Handles subsequent turns (rebuttal, synthesis).
    -   `worker-low-priority`: Handles the final report generation.

-   **PostgreSQL Database (`db`)**: The primary data store for all persistent data, including rooms, messages, user profiles, and reviews. It uses two key extensions:
    -   `pgvector`: For high-performance semantic similarity searches on memory embeddings.
    -   `pgcrypto`: For field-level encryption of sensitive user data.

-   **PgBouncer**: A lightweight connection pooler that sits in front of the PostgreSQL database. It reduces the overhead of creating new connections for each request, significantly improving performance and stability under load.

-   **Redis**: Serves two critical roles:
    -   **Celery Broker & Backend**: Manages the message queue for tasks between the API server and the Celery workers.
    -   **Pub/Sub for WebSockets**: Provides a scalable backplane for broadcasting real-time messages from the backend (Celery workers or API) to all connected WebSocket clients, regardless of which API server instance they are connected to.

-   **React Frontend**: A modern, single-page application (SPA) built with React and Vite. It uses `@tanstack/react-query` for robust server state management, handling data fetching, caching, and synchronization automatically. It communicates with the backend via HTTP and WebSocket protocols.

## 2. Observability and Debugging

To ensure the system is maintainable and easy to debug, a unified tracing system has been implemented.

-   **Trace ID**: When a new review is initiated via the API, a unique `trace_id` is generated. This ID is passed through the entire Celery task chain and is included in all log messages related to that request. This allows for easy filtering and correlation of logs across the distributed services (API server and Celery workers) to trace the full lifecycle of a single review process.
-   **Structured Logging**: Logs are structured to include the `trace_id`, making it simple to query and analyze logs in a centralized logging platform.

## 3. Multi-Agent Review Flow

The review process is designed to be configurable and resilient.

- **Configurability**: The API endpoint for creating a review (`POST /api/rooms/{sub_room_id}/reviews`) accepts an optional `panelists` array (e.g., `["openai", "gemini"]`). If not provided, it defaults to using all three configured providers (OpenAI, Gemini, Claude). A global `FORCE_DEFAULT_PROVIDER` setting can also be used to force all reviews to use a single AI for debugging or cost-saving.
- **Fallback Logic**: During the initial analysis round, if a requested provider (e.g., Gemini) fails for any reason (API error, timeout), the system automatically falls back and re-runs that panelist's turn using the default provider (OpenAI). This ensures the debate can continue with the full number of panelists. The failure and fallback are logged in the review's metrics.


## 4. Real-time WebSocket Flow

The real-time review status update mechanism is a key feature that demonstrates the interaction between several components.

1.  **Connection**: The React frontend establishes a WebSocket connection to the `/ws/reviews/{review_id}` endpoint, passing a JWT for authentication. The Nginx proxy upgrades this connection and forwards it to an available FastAPI server instance.
2.  **Authentication**: The FastAPI backend validates the JWT and verifies that the authenticated user owns the requested review. If successful, the connection is added to an in-memory `ConnectionManager`.
3.  **Task Execution**: A user action triggers a Celery task (e.g., starting a review). The task is sent to the Redis message broker.
4.  **Task Processing**: A Celery worker picks up the task from the appropriate queue and begins processing.
5.  **Broadcasting**: As the Celery worker completes a milestone (e.g., a review round), it publishes a status update message to a specific Redis Pub/Sub channel (e.g., `review_{review_id}`).
6.  **Listening**: All FastAPI server instances are running a background task that listens to the Redis Pub/Sub channels. When a message is received, each server instance checks its local `ConnectionManager`.
7.  **Push to Client**: If a server instance has a client connected for that specific `review_id`, it pushes the message down the appropriate WebSocket.

This architecture ensures that the system is decoupled, scalable, and can provide real-time updates efficiently.
