from fastapi.testclient import TestClient

class TestAuthSmoke:
    """
    A minimal set of tests to ensure the basic application and test setup are working.
    """

    def test_health_endpoint_accessible(self, client: TestClient):
        """Test that health endpoint is accessible without authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
