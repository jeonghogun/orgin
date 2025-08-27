"""
Review Service - Orchestrates the multi-agent review process using Celery.
"""
import logging
from app.services.storage_service import StorageService
from app.tasks.review_tasks import run_initial_panel_turn

logger = logging.getLogger(__name__)


class ReviewService:
    """Orchestrates the multi-agent, multi-round review process."""

    def __init__(self, storage_service: StorageService) -> None:
        """Initialize the review service."""
        super().__init__()
        self.storage: StorageService = storage_service

    def start_review_process(self, review_id: str, topic: str, instruction: str) -> None:
        """
        Starts the asynchronous review process by kicking off the Celery task chain.
        """
        logger.info(f"Dispatching Celery task chain for review_id: {review_id}")

        # Start the chain by calling the first task.
        # The subsequent tasks will be called by the previous task in the chain.
        run_initial_panel_turn.delay(
            review_id=review_id, topic=topic, instruction=instruction
        )
