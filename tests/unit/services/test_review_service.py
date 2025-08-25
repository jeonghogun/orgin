import pytest
from unittest.mock import AsyncMock, patch

from app.services.review_service import ReviewService
from app.models.schemas import ReviewMeta

@pytest.fixture
def review_service():
    """Fixture to create a ReviewService instance."""
    return ReviewService()

class TestReviewService:
    """Tests for the ReviewService."""

    @pytest.mark.anyio
    @patch("app.services.review_service.storage_service", new_callable=AsyncMock)
    @patch("app.services.review_service.llm_service", new_callable=AsyncMock)
    async def test_execute_review_happy_path(self, mock_llm_service, mock_storage_service):
        """
        Test the full, successful execution of the 3-round review process.
        """
        review_id = "test-review-123"
        review_service = ReviewService()

        # Setup mocks
        mock_storage_service.get_review_meta.return_value = ReviewMeta(
            review_id=review_id,
            room_id="test-room",
            topic="Test Topic",
            instruction="Test instruction",
            status="in_progress",
            total_rounds=3,
            created_at=12345
        )
        # Configure the mock for get_provider
        mock_provider = AsyncMock()
        mock_provider.invoke.return_value = {"content": '{"summary": "Mocked analysis"}'}

        # get_provider is a sync method returning an async provider
        from unittest.mock import MagicMock
        mock_llm_service.get_provider = MagicMock(return_value=mock_provider)

        # Execute the service method
        await review_service.execute_review(review_id)

        # Assertions
        mock_storage_service.get_review_meta.assert_called_once_with(review_id)
        assert mock_storage_service.log_review_event.call_count == 23
        assert mock_provider.invoke.call_count == 10
        mock_storage_service.save_final_report.assert_called_once()

        final_status_call = mock_storage_service.update_review.call_args
        assert final_status_call.args[0] == review_id
        assert final_status_call.args[1]["status"] == "completed"
        assert "completed_at" in final_status_call.args[1]

    @pytest.mark.anyio
    @patch("app.services.review_service.storage_service", new_callable=AsyncMock)
    @patch("app.services.review_service.llm_service", new_callable=AsyncMock)
    async def test_execute_review_ai_failure(self, mock_llm_service, mock_storage_service):
        """
        Test the review process when one of the AI panelists fails.
        """
        review_id = "test-review-fail-123"
        review_service = ReviewService()

        mock_storage_service.get_review_meta.return_value = ReviewMeta(
            review_id=review_id,
            room_id="test-room",
            topic="Test Topic",
            instruction="Test instruction",
            status="in_progress",
            total_rounds=3,
            created_at=12345
        )

        mock_provider = AsyncMock()
        async def invoke_side_effect(*args, **kwargs):
            if "Claude" in kwargs.get("request_id", ""):
                raise Exception("AI panelist failed")
            return {"content": '{"summary": "Mocked analysis"}'}
        mock_provider.invoke.side_effect = invoke_side_effect

        from unittest.mock import MagicMock
        mock_llm_service.get_provider = MagicMock(return_value=mock_provider)

        await review_service.execute_review(review_id)

        final_status_call = mock_storage_service.update_review.call_args_list[-1]
        assert final_status_call.args[1]["status"] == "completed"

        error_event_logged = False
        for call in mock_storage_service.log_review_event.call_args_list:
            event = call.args[0]
            if event.get("type") == "panel_error" and "Claude" in event.get("actor", ""):
                error_event_logged = True
                break
        assert error_event_logged is True
