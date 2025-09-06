# Release Notes: Conversation Feature v2

This release implements the full suite of features for the new GPT-like conversational interface, following a structured, step-by-step development plan.

## ✨ New Features

- **Conversational Interface:** A complete real-time, streaming chat UI has been implemented using React, Zustand, and React Query.
- **Backend API:** A new set of endpoints under `/api/convo/*` provides robust support for thread management, message history, editing, and SSE streaming.
- **LLM Abstraction:** A flexible adapter pattern has been implemented to support various LLM providers (OpenAI, Anthropic, Google), with a complete, production-ready implementation for OpenAI.
- **File Uploads & RAG:** Users can now upload files, which are processed in the background by a Celery worker. The system extracts text, creates vector embeddings, and uses this information for Retrieval-Augmented Generation (RAG) to provide context-aware answers.
- **Cost, Usage & Budgeting:**
    - Token usage and estimated costs are calculated for each message and displayed in the UI.
    - A daily token budget system has been implemented using Redis to prevent excessive usage.
- **Monitoring:** Custom Prometheus metrics for LLM calls, latency, and token counts have been integrated for enhanced observability.
- **Testing:** Unit and Integration test suites have been added to ensure the stability and correctness of the new services and APIs.

## 💥 Breaking Changes

- None. All new features are additive and exist within new tables and API namespaces, ensuring no impact on the existing application.

## 🚀 Migration and Deployment

### 1. Database Migrations
Run the following command to apply the new database schema:
```bash
# Note: In the sandbox, this command may fail. It should be run in a configured local/CI environment.
alembic upgrade head
```
This adds the `attachments`, `conversation_threads`, `conversation_messages`, and `attachment_chunks` tables.

### 2. Dependencies
Ensure new Python (`sse-starlette`, `pypdf2`) and Node.js (`zustand`, `immer`, `@heroicons/react`) dependencies are installed.

### 3. Environment Variables
Configure the following in your `.env` file:
```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
DAILY_TOKEN_BUDGET=200000
```

### 4. Nginx for SSE
Update your Nginx configuration to disable buffering for the `/api/convo/messages/` location to ensure SSE works correctly.

## ⚠️ Known Issues & Limitations

- **RAG Hybrid Search:** The planned BM25 keyword search for hybrid RAG has not been implemented; the current RAG is vector-search-only.
- **Frontend Polish:** Advanced UI features like a model/temperature switcher, `DiffView`, and a command palette are not yet implemented.
- **Error Handling:** UI feedback for API/SSE errors can be improved.
- **Test Environment:** The test suite could not be run directly within the sandbox due to environment configuration issues. The tests have been written and are included in the patch but must be run in a properly configured CI/CD or local development environment.

## 🧪 Running Tests in CI/CD

To run the test suite in a CI/CD pipeline, the following steps are required:

1.  **Set up Services:** The integration tests require a running PostgreSQL (with pgvector) and Redis instance. Use Docker or your CI platform's service containers to launch these. The connection details should be passed as environment variables (e.g., `DATABASE_URL`, `REDIS_URL`).
2.  **Install Dependencies:** Install both production and development dependencies.
    ```bash
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
    ```
3.  **Reset Test Database:** Before running the tests, ensure the test database is in a clean state. The `scripts/reset_test_db.sh` script is provided for this purpose. It applies all Alembic migrations.
    ```bash
    ./scripts/reset_test_db.sh
    ```
4.  **Run Pytest:** Execute `pytest` from the root of the repository. It will automatically discover and run all tests.
    ```bash
    pytest
    ```
