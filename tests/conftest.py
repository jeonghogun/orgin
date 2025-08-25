import pytest
from unittest.mock import patch

# This patch must be applied before the app is imported.
with patch("psycopg2.connect") as mock_connect:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config.settings import settings

USER_ID = "test-conftest-user"



@pytest.fixture(scope="session")
def client():
    """A TestClient instance for the FastAPI app."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authenticated_client(client: TestClient, monkeypatch):
    """
    A TestClient that is pre-authenticated. It patches the firebase token verification
    to always return a valid user and sets AUTH_OPTIONAL to False.
    """
    # Ensure auth is mandatory for these tests
    monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)

    with patch("firebase_admin.auth.verify_id_token") as mock_verify_token:
        mock_verify_token.return_value = {"uid": USER_ID}
        client.headers["Authorization"] = "Bearer test-token"
        yield client

    # Reset auth setting and headers after test
    monkeypatch.setattr(settings, "AUTH_OPTIONAL", True)
    client.headers.pop("Authorization", None)
