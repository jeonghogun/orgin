import pytest
import testing.postgresql
import psycopg2
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.config.settings import settings

USER_ID = "test-conftest-user"

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
    Overrides the database URL setting for the entire test session.
    """
    original_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db.url()
    yield
    settings.DATABASE_URL = original_db_url


@pytest.fixture(scope="function")
def db_session(test_db):
    """
    Provides a clean database state for each test function.
    It clears all tables before each test.
    """
    conn = psycopg2.connect(test_db.url())
    cursor = conn.cursor()

    tables = [
        "review_metrics", "user_profiles", "review_events",
        "reviews", "messages", "rooms"
    ]

    for table in tables:
        cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
    conn.commit()

    yield conn

    conn.close()


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

@pytest.fixture(autouse=True)
def patch_llm_service(monkeypatch):
    """
    Automatically mocks the llm_service wherever it is used to prevent
    real API calls during testing.
    """
    mock_llm = AsyncMock()
    mock_llm.generate_embedding.return_value = [0.0] * 1536

    mock_provider = AsyncMock()
    mock_provider.invoke.return_value = "Mocked AI Response"
    mock_llm.get_provider.return_value = mock_provider

    import app.services.storage_service as storage_mod
    import app.services.rag_service as rag_mod
    import app.services.memory_service as memory_mod
    import app.services.intent_service as intent_mod
    import app.services.review_service as review_mod

    monkeypatch.setattr(storage_mod, "llm_service", mock_llm, raising=False)
    monkeypatch.setattr(memory_mod, "llm_service", mock_llm, raising=False)
    monkeypatch.setattr(intent_mod, "llm_service", mock_llm, raising=False)
    monkeypatch.setattr(review_mod, "llm_service", mock_llm, raising=False)
    monkeypatch.setattr(rag_mod, "llm", mock_llm, raising=False)
