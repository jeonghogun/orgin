import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session", autouse=True)
def disable_rate_limiting_for_tests():
    """Disable rate limiting for all tests by setting an environment variable."""
    os.environ["RATE_LIMITING_DISABLED"] = "true"
    yield
    if "RATE_LIMITING_DISABLED" in os.environ:
        del os.environ["RATE_LIMITING_DISABLED"]

@pytest.fixture(scope="function")
def client():
    """
    A TestClient fixture.
    """
    with TestClient(app) as c:
        yield c
