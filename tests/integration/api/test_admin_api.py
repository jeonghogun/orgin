import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import require_role, require_auth

# Mock user data
MOCK_REGULAR_USER = {"user_id": "user123", "role": "user"}
MOCK_ADMIN_USER = {"user_id": "admin456", "role": "admin"}

# Override dependencies for testing
def override_require_auth_regular():
    return MOCK_REGULAR_USER

def override_require_auth_admin():
    return MOCK_ADMIN_USER

def get_test_client_for_user(user_type: str) -> TestClient:
    """Returns a TestClient with authentication overrides for a specific user type."""
    if user_type == "admin":
        app.dependency_overrides[require_auth] = override_require_auth_admin
    elif user_type == "user":
        app.dependency_overrides[require_auth] = override_require_auth_regular

    # The require_role dependency needs to be overridden to *not* trigger
    # as we are testing the router-level dependency which runs before it.
    # For a real test with a DB, we would mock the `memory_service.get_user_profile` call.
    # Here, we just ensure it doesn't block the test.
    def mock_require_role_factory(role):
        def mock_role_checker():
            if user_type == role:
                return user_type
            # This part won't be hit if router dependency works, but as a fallback:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return mock_role_checker

    app.dependency_overrides[require_role] = mock_require_role_factory

    return TestClient(app)


def test_admin_dashboard_unauthenticated():
    """Tests that unauthenticated users cannot access admin routes."""
    # No auth override, so it should fail
    app.dependency_overrides = {}
    client = TestClient(app)
    response = client.get("/api/admin/dashboard")
    # Because AUTH_OPTIONAL is now False, this should be a 401
    assert response.status_code == 401

def test_admin_dashboard_as_regular_user():
    """Tests that regular users receive a 403 Forbidden error."""
    client = get_test_client_for_user("user")
    # We need to mock the service it calls to avoid other errors
    from app.api.dependencies import get_admin_service
    from unittest.mock import MagicMock

    mock_admin_service = MagicMock()
    mock_admin_service.get_dashboard_kpis.return_value = {}

    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service

    response = client.get("/api/admin/dashboard")
    assert response.status_code == 403

def test_admin_dashboard_as_admin():
    """Tests that admin users can access the dashboard."""
    client = get_test_client_for_user("admin")
    from app.api.dependencies import get_admin_service
    from unittest.mock import MagicMock

    mock_admin_service = MagicMock()
    mock_admin_service.get_dashboard_kpis.return_value = {"test": "data"}

    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service

    response = client.get("/api/admin/dashboard")
    assert response.status_code == 200
    assert response.json() == {"test": "data"}

# Cleanup overrides after tests
@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides = {}
