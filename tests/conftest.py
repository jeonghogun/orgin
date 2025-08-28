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
    def on_initialized(postgresql):
        with psycopg2.connect(postgresql.url()) as conn:
            with conn.cursor() as cursor:
                with open("app/db/schema.sql", "r") as f:
                    cursor.execute(f.read())
            conn.commit()

    return testing.postgresql.PostgresqlFactory(cache_initialized_db=True, on_initialized=on_initialized)


@pytest.fixture(scope="session")
def test_db(postgresql_factory):
    """Create a temporary database instance for the test session."""
    postgresql = postgresql_factory()
    yield postgresql
    postgresql.stop()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(test_db):
    """
    Overrides settings for the entire test session.
    """
    original_db_url = settings.DATABASE_URL
    original_testing = settings.TESTING
    original_key = settings.DB_ENCRYPTION_KEY

    settings.DATABASE_URL = test_db.url()
    settings.TESTING = True
    settings.DB_ENCRYPTION_KEY = "test-encryption-key-32-bytes-long" # Must be long enough

    yield

    settings.DATABASE_URL = original_db_url
    settings.TESTING = original_testing
    settings.DB_ENCRYPTION_KEY = original_key


@pytest.fixture(scope="function")
def db_session(test_db):
    """
    Provides a clean database state for each test function.
    It clears all tables before each test.
    """
    conn = psycopg2.connect(test_db.url())
    cursor = conn.cursor()

    tables = [
        "review_metrics", "conversation_contexts", "user_profiles", "review_events",
        "reviews", "messages", "memories", "rooms"
    ]

    for table in tables:
        cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
    conn.commit()

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

