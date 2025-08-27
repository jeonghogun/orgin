from unittest.mock import AsyncMock
from app.main import app
from app.api.dependencies import get_search_service

# Mock data to be returned by the search service
MOCK_SEARCH_RESULTS = {"some_key": "some_value"}


class TestSearchAPI:
    """Tests for the /api/search endpoints."""

    def test_search_success(self, client):
        """Test successful search."""
        mock_search_service = AsyncMock()
        mock_search_service.web_search.return_value = MOCK_SEARCH_RESULTS
        app.dependency_overrides[get_search_service] = lambda: mock_search_service

        response = client.get("/api/search?q=artificial+intelligence")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["query"] == "artificial intelligence"
        assert data["results"] == MOCK_SEARCH_RESULTS
        mock_search_service.web_search.assert_called_once_with("artificial intelligence", 5)
        app.dependency_overrides = {}

    def test_search_no_query(self, client):
        """Test search with no query parameter."""
        response = client.get("/api/search")
        assert response.status_code == 422  # Unprocessable Entity from FastAPI

    def test_search_rag_service_error(self, client):
        """Test handling of an error from the search service."""
        mock_search_service = AsyncMock()
        mock_search_service.web_search.side_effect = Exception("Service is down")
        app.dependency_overrides[get_search_service] = lambda: mock_search_service

        response = client.get("/api/search?q=deep+learning")

        assert response.status_code == 500
        assert "Search failed" in response.json()["detail"]
        app.dependency_overrides = {}
