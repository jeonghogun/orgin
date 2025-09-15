# Performance & Load Testing Guide

This document provides instructions for running load tests against the Origin Project API using Locust. It also outlines expected bottlenecks and areas to monitor during testing.

## 1. Overview

The provided `locustfile.py` script simulates user behavior to test the system under load. The primary goals are to:
- Ensure the system remains stable with 20-50 concurrent users.
- Identify performance bottlenecks in the application stack.
- Measure key performance indicators (KPIs) like response time and failure rate under stress.

**Note:** This test cannot be run in the provided sandbox environment due to execution and networking limitations. It must be run from a local developer machine against a running instance of the application.

## 2. Setup and Execution

### Step 1: Install Locust
```bash
pip install locust
```

### Step 2: Run the Application Stack
Ensure the full application stack (API, database, Redis, Celery workers) is running. The recommended way to do this is with the main `docker-compose.yml` file:
```bash
# Make sure to create a .env file from .env.example first
docker-compose up -d --build
```
This will start the API server on `localhost:8080` (via Nginx).

### Step 3: Run the Load Test
Start the Locust test from your terminal in the project's root directory.

```bash
locust
```

### Step 4: Configure and Start the Test
1.  Open your web browser and navigate to `http://localhost:8089`.
2.  **Number of users:** Enter the total number of concurrent users to simulate (e.g., `50`).
3.  **Spawn rate:** Enter the number of users to start per second (e.g., `5`).
4.  **Host:** The host should already be set to `http://localhost:8080`, which is the default in the `locustfile.py`.
5.  Click "Start swarming".

You can now monitor the statistics, charts, and failures in the Locust web UI.

## 3. Key Scenarios Simulated

The `locustfile.py` simulates the following user actions:
- **`send_chat_message` (5x weight):** The most common action. A user sends a message to their main room, triggering the RAG and streaming response logic.
- **`list_rooms` (2x weight):** A user fetches their list of rooms.
- **`create_sub_room_and_start_review` (1x weight):** The most resource-intensive action. A user creates a sub-room and immediately kicks off a new AI review process, which involves multiple Celery tasks and LLM calls.

## 4. Expected Bottlenecks & What to Monitor

During the load test, pay close attention to the following areas, as they are the most likely sources of performance issues.

1.  **Celery Worker Saturation:**
    - **Symptom:** The AI review process (`create_sub_room_and_start_review` tasks) will show very high response times or start to fail in Locust. Chat messages may also become slow if workers are starved.
    - **Why:** The number of concurrent Celery workers is fixed. With many users starting reviews simultaneously, all worker processes could become occupied, leading to long queue times for all background tasks.
    - **Monitoring:** Use a tool like Flower (not included, but can be added to `docker-compose`) to monitor Celery queue lengths and worker status.

2.  **Database Connection Pool:**
    - **Symptom:** API endpoints will return 5xx errors, and logs will show "cannot get a connection from the pool" or similar errors from `pgbouncer`.
    - **Why:** The number of available database connections is finite. High concurrency across the API and all Celery workers can exhaust the connection pool managed by `pgbouncer`.
    - **Monitoring:** Check the `pgbouncer` logs. In a production setup, monitor active DB connections in your database monitoring tool.

3.  **LLM API Rate Limiting:**
    - **Symptom:** Locust will report failures for chat and review tasks, with logs showing 429 (Too Many Requests) errors from the external LLM providers (OpenAI, Anthropic, Gemini).
    - **Why:** External API providers have strict rate limits. A sudden burst of 50 concurrent users all making LLM calls will likely exceed these limits.
    - **Monitoring:** Check application logs for HTTP 429 errors from LLM service calls.

4.  **WebSocket Connections (If applicable to chat in future):**
    - **Symptom:** If chat were WebSocket-based, you would see connection failures.
    - **Why:** Each server has a limit on the number of open file descriptors, which limits the number of concurrent WebSocket connections.
    - **Monitoring:** Check server-level metrics for open file descriptors and WebSocket connection counts.
