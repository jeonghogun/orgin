# Origin Project Operations Runbook

This document provides operational guidance for running and maintaining the Origin project in a production environment.

## 1. Secrets Management & Rotation

The application's secrets are managed via a `SecretProvider` abstraction. The default provider sources secrets from environment variables.

### Key Rotation Procedure

To rotate a secret (e.g., `OPENAI_API_KEY`, `DB_ENCRYPTION_KEY`):

1.  **Generate a new key/secret.**
2.  **Update the secret in your secret management system** (e.g., your cloud provider's secret manager, HashiCorp Vault, or the environment variables for your Docker containers).
3.  **Perform a rolling restart of the affected services.**
    -   For API key changes (`OPENAI_API_KEY`, etc.), restart the `api`, `worker-default`, `worker-high-priority`, and `worker-low-priority` services.
    -   For `DB_ENCRYPTION_KEY` changes, a data migration is required, and this should be handled with extreme care. See the data migration section. A simple restart is **not** sufficient.

**Command for restarting services (Docker Compose):**
```bash
# To restart a specific service
docker compose restart api

# To restart all services and apply changes
docker compose up -d --remove-orphans
```

## 2. Database Migrations (Alembic)

Database schema changes are managed by Alembic.

-   **Applying Migrations:** To apply all pending migrations to the database, run the following command from a machine that can connect to the database (or inside the `api` container):
    ```bash
    alembic -c /app/alembic.ini upgrade head
    ```
    In a Docker Compose setup, this is typically:
    ```bash
    docker compose exec api alembic upgrade head
    ```
    This should be part of your deployment pipeline, run after the code is updated but before the application is switched to the new version.

-   **Checking Status:** To see the current migration status:
    ```bash
    docker compose exec api alembic current
    ```

## 3. Incident Response Runbooks

### 3.1. Incident: High LLM Provider Error Rate

-   **Detection:**
    -   Prometheus alert `ProviderErrorRateHigh` fires for a specific provider.
    -   Spike in `origin_llm_calls_total{outcome="failure"}` metric.
    -   Users report reviews failing to start or complete.
-   **Immediate Actions:**
    1.  **Check Provider Status Page:** Visit the status page for the failing provider (e.g., OpenAI, Anthropic, Google) to check for a global outage.
    2.  **Force Fallback (Temporary Mitigation):** If a single provider is failing, you can set the `FORCE_DEFAULT_PROVIDER=True` environment variable and restart the `api` and `worker` containers. This will route all LLM traffic through your default provider (typically OpenAI), restoring service at the cost of provider diversity.
-   **Recovery:**
    1.  Once the provider's service is restored, set `FORCE_DEFAULT_PROVIDER=False` and perform another rolling restart.
    2.  Manually inspect any reviews that failed during the outage and decide whether to re-trigger them.

### 3.2. Incident: Celery Tasks Are Stuck

-   **Detection:**
    -   Reviews are stuck in the "in_progress" state for an extended period.
    -   No new logs from the Celery worker containers.
    -   Redis queue length (viewable with `redis-cli LLEN celery`) is growing but not shrinking.
-   **Immediate Actions:**
    1.  **Check Worker Logs:** Inspect the logs for all worker containers for tracebacks or error messages.
        ```bash
        docker compose logs worker-default
        ```
    2.  **Check Redis Connection:** Ensure workers can connect to the Redis broker. Check for Redis server logs or connectivity issues.
    3.  **Restart Workers:** A rolling restart of the worker containers is often the quickest way to resolve transient issues.
        ```bash
        docker compose restart worker-default worker-high-priority worker-low-priority
        ```
-   **Recovery:**
    -   The retry logic built into the Celery tasks should handle most transient failures. Once the workers are back online, they should pick up and retry the failed tasks automatically.

### 3.3. Incident: Database Failure / Unavailability

-   **Detection:**
    -   API and worker logs are filled with `psycopg2.OperationalError`.
    -   The `/health` endpoint may be down or slow.
    -   All API requests that touch the database fail with 5xx errors.
-   **Immediate Actions:**
    1.  **Check Database Status:** Verify that the PostgreSQL container or service is running and healthy. Check its logs for any errors.
    2.  **Check PgBouncer:** Ensure the `pgbouncer` connection pooler is running and can connect to the main database. Check its logs.
    3.  **Failover (if configured):** If you have a standby replica, initiate the database failover procedure as per your infrastructure provider's documentation.
-   **Recovery:**
    1.  Once the database is back online, restart all application services (`api`, workers) to re-establish fresh connections through the pooler.
        ```bash
        docker compose restart api worker-default worker-high-priority worker-low-priority
        ```

### 3.4. Incident: Poor RAG/Memory Retrieval Quality

-   **Detection:**
    -   Users report that the AI's responses are not context-aware or seem to be missing relevant information from past conversations.
    -   Internal testing shows that queries are not returning the expected memories.
-   **Immediate Actions (Debugging):**
    1.  **Use the Admin Preview Endpoint:** There is a protected admin endpoint that allows you to see the raw results of the hybrid retrieval process for a given query. This is the most powerful tool for debugging.
        ```bash
        # Make sure to replace placeholders and use a valid admin auth token
        curl -X GET -H "Authorization: Bearer <ADMIN_TOKEN>" \
        "http://localhost:8080/api/admin/memory/preview?room_id=<ROOM_ID>&q=<QUERY>"
        ```
        This will return the scored and ranked list of messages that the RAG service is using as context. You can inspect the scores, see if the expected messages are present, and analyze the influence of BM25 vs. vector search.
    2.  **Check Retrieval Metrics:** Look at the `retrieval.*` metrics in Prometheus to see if the number of candidates from BM25 and vector searches are as expected. A low number of candidates could indicate an issue with the query or the indexes.
    3.  **Tune Hybrid Search Weights:** If one retrieval method (e.g., text search) is consistently outperforming the other, you can adjust the weights (`HYBRID_BM25_WEIGHT`, `HYBRID_VEC_WEIGHT`) via environment variables and restart the `api` service to tune the results.
