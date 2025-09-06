# Load environment variables from .env.example for test collection
from dotenv import load_dotenv
load_dotenv(dotenv_path='.env.example')

import pytest
import testing.postgresql
import psycopg2
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.config.settings import settings
import json

USER_ID = "test-conftest-user"

# A mock function to simulate LLM provider responses for E2E tests
async def mock_llm_invoke(model, system_prompt, user_prompt, request_id, response_format="json", **kwargs):
    """
    Mocks the LLM API call for E2E testing.
    It returns a canned response based on the persona in the system_prompt.
    """
    # For summarization tasks
    if "You are a summarization AI" in system_prompt:
        return json.dumps({"summary": "This is a summary."}), {"total_tokens": 10}

    # For final report generation
    if "You are a Reporter AI" in system_prompt or "마스터 전략가" in system_prompt:
        report = {
            "topic": "E2E Test Topic",
            "executive_summary": "This is the executive summary.",
            "perspective_summary": {},
            "alternatives": ["Alternative 1"],
            "recommendation": "adopt",
            "round_summary": "The final round summary.",
            "evidence_sources": []
        }
        return json.dumps(report), {"total_tokens": 50}

    # For panelist analysis
    persona = "Unknown Persona"
    if "AGI 비관론자" in system_prompt:
        persona = "AGI 비관론자"
    elif "AGI 낙관론자" in system_prompt:
        persona = "AGI 낙관론자"
    elif "AGI 중립론자" in system_prompt:
        persona = "AGI 중립론자"

    analysis = {
        "summary": f"Summary from {persona}",
        "key_points": ["Point 1", "Point 2"],
        "concerns": ["Concern 1"],
        "recommendations": ["Recommendation 1"]
    }

    return json.dumps(analysis), {"total_tokens": 20}

@pytest.fixture(scope="session")
def postgresql_factory():
    """Factory for creating temporary PostgreSQL instances."""
    # This factory is cached for the entire test session.
    return testing.postgresql.PostgresqlFactory(cache_initialized_db=True)


@pytest.fixture(scope="session")
def test_db():
    """
    Use Docker PostgreSQL database for tests.
    """
    class MockDB:
        def url(self):
            # Use separate test database for complete isolation
            return "postgresql://user:password@localhost:5433/test_origin_db"

        def stop(self):
            # Nothing to stop since we're using an external DB.
            pass
    
    yield MockDB()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(test_db):
    """
    Overrides settings for the entire test session.
    """
    original_db_url = settings.DATABASE_URL
    original_testing = settings.TESTING
    original_key = settings.DB_ENCRYPTION_KEY
    original_redis_url = settings.REDIS_URL
    original_celery_broker = settings.CELERY_BROKER_URL
    original_celery_backend = settings.CELERY_RESULT_BACKEND

    settings.DATABASE_URL = test_db.url()
    settings.TESTING = True
    settings.DB_ENCRYPTION_KEY = "test-encryption-key-32-bytes-long" # Must be long enough
    settings.REDIS_URL = "redis://localhost:6379/0"
    settings.CELERY_BROKER_URL = "redis://localhost:6379/0"
    settings.CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

    yield

    settings.DATABASE_URL = original_db_url
    settings.TESTING = original_testing
    settings.DB_ENCRYPTION_KEY = original_key
    settings.REDIS_URL = original_redis_url
    settings.CELERY_BROKER_URL = original_celery_broker
    settings.CELERY_RESULT_BACKEND = original_celery_backend


def _reset_test_database():
    """
    Safely reset test database to clean state.
    Only runs in test environment to avoid affecting production.
    """
    import subprocess
    import os
    
    # Only run in test environment
    if not os.getenv("PYTEST_CURRENT_TEST"):
        return
    
    try:
        # Run the reset script
        result = subprocess.run(
            ["./scripts/reset_test_db.sh"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        if result.returncode != 0:
            print(f"Warning: Database reset failed: {result.stderr}")
    except Exception as e:
        print(f"Warning: Could not reset database: {e}")


@pytest.fixture(scope="function")
def db_session(test_db):
    """
    Provides a clean database state for each test function.
    Automatically resets database before each test for complete isolation.
    """
    # Reset database before each test
    _reset_test_database()
    
    conn = psycopg2.connect(str(test_db.url()))
    yield conn
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def celery_eager(request):
    """
    Forces celery tasks to run synchronously for the entire test session.
    This makes debugging much easier and avoids race conditions.
    """
    from app.celery_app import celery_app
    celery_app.conf.update(task_always_eager=True)


@pytest.fixture(scope="function")
def client(db_session):
    """
    A TestClient instance for the FastAPI app that is connected to the test database.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_audit_service():
    """Fixture for a mocked AuditService."""
    from unittest.mock import MagicMock
    return MagicMock()


@pytest.fixture
def authenticated_client(client: TestClient):
    """
    A TestClient that is pre-authenticated and connected to the test database.
    """
    original_auth_optional = settings.AUTH_OPTIONAL
    settings.AUTH_OPTIONAL = False

    with patch("firebase_admin.auth.verify_id_token") as mock_verify_token:
        mock_verify_token.return_value = {"uid": USER_ID}
        client.headers["Authorization"] = "Bearer test-token"
        yield client

    settings.AUTH_OPTIONAL = original_auth_optional
    client.headers.pop("Authorization", None)

