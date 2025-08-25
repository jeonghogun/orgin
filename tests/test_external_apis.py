import pytest
from unittest.mock import AsyncMock, patch

# Mock data to be returned by the search service
MOCK_SEARCH_RESULTS = {"some_key": "some_value"}


@patch("app.api.routes.search.external_search_service", new_callable=AsyncMock)
class TestSearchAPI:
    """Tests for the /api/search endpoints."""

    def test_search_success(self, mock_search_service, client):
        """Test successful search."""
        mock_search_service.web_search.return_value = MOCK_SEARCH_RESULTS

        response = client.get("/api/search?q=artificial+intelligence")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["query"] == "artificial intelligence"
        assert data["results"] == MOCK_SEARCH_RESULTS
        mock_search_service.web_search.assert_called_once_with("artificial intelligence", 5)

    def test_search_no_query(self, mock_search_service, client):
        """Test search with no query parameter."""
        response = client.get("/api/search")
        assert response.status_code == 422  # Unprocessable Entity from FastAPI

    def test_search_rag_service_error(self, mock_search_service, client):
        """Test handling of an error from the search service."""
        mock_search_service.web_search.side_effect = Exception("Service is down")

        response = client.get("/api/search?q=deep+learning")

        assert response.status_code == 500
        assert "Search failed" in response.json()["detail"]
