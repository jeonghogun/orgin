"""
Review Service - Orchestrates the multi-agent review process using Celery.
"""
import logging
import uuid
from typing import Optional, List, Dict, Any

from app.services.storage_service import StorageService
from app.celery_app import celery_app
from app.models.schemas import Room, ReviewMeta, CreateReviewRoomInteractiveResponse
from app.models.enums import RoomType
from app.utils.helpers import generate_id, get_current_timestamp
from app.api.dependencies import get_conversation_service, get_llm_service
from app.core.errors import InvalidRequestError

logger = logging.getLogger(__name__)


class ReviewService:
    """Orchestrates the multi-agent, multi-round review process."""

    def __init__(self, storage_service: StorageService) -> None:
        """Initialize the review service."""
        super().__init__()
        self.storage: StorageService = storage_service

    async def start_review_process(
        self, review_id: str, review_room_id: str, topic: str, instruction: str, panelists: Optional[List[str]], trace_id: str
    ) -> None:
        """
        Starts the asynchronous review process by kicking off the Celery task chain.
        """
        logger.info(f"Dispatching Celery task chain for review_id: {review_id} with trace_id: {trace_id}")

        # Use .delay() to call the task, which respects task_always_eager for tests.
        # Access the task from the app's registry by name to avoid circular imports.
        task = celery_app.tasks.get("app.tasks.review_tasks.run_initial_panel_turn")
        if task:
            task.delay(
                review_id=review_id,
                review_room_id=review_room_id,
                topic=topic,
                instruction=instruction,
                panelists_override=panelists,
                trace_id=trace_id,
            )
        else:
            # This would indicate a configuration error
            logger.error("Could not find Celery task: app.tasks.review_tasks.run_initial_panel_turn")

    async def create_interactive_review(
        self,
        parent_id: str,
        topic: str,
        user_id: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> CreateReviewRoomInteractiveResponse:
        """
        Interactively creates a review room, consolidating logic from the API layer.
        """
        parent_room = self.storage.get_room(parent_id)
        if not parent_room or parent_room.type != RoomType.SUB:
            raise InvalidRequestError("Parent room must be a sub-room.")

        conversation_service = get_conversation_service()
        llm_service = get_llm_service()

        threads = await conversation_service.get_threads_by_room(parent_id)
        full_conversation = ""
        for thread in threads:
            messages = await conversation_service.get_all_messages_by_thread(thread.id)
            for msg in messages:
                full_conversation += f"{msg['role']}: {msg['content']}\n"

        context_sufficient = topic.lower() in full_conversation.lower()
        if history and len(history) > 0:
            context_sufficient = True

        if context_sufficient:
            room_id = generate_id()
            new_room = self.storage.create_room(
                room_id=room_id,
                name=f"검토: {topic}",
                owner_id=user_id,
                room_type=RoomType.REVIEW,
                parent_id=parent_id,
            )

            review_id = generate_id()
            instruction = "이 주제에 대해 3 라운드에 걸쳐 심도 있게 토론해주세요."
            review_meta = ReviewMeta(
                review_id=review_id,
                room_id=room_id,
                topic=topic,
                instruction=instruction,
                status="pending",
                total_rounds=3,
                created_at=get_current_timestamp(),
            )
            self.storage.save_review_meta(review_meta)

            trace_id = str(uuid.uuid4())
            await self.start_review_process(
                review_id=review_id,
                review_room_id=room_id,
                topic=topic,
                instruction=instruction,
                panelists=None, # Panelists can be selected in a more advanced flow
                trace_id=trace_id,
            )

            return CreateReviewRoomInteractiveResponse(status="created", room=Room.model_validate(new_room))
        else:
            system_prompt = "You are an AI assistant helping a user create a 'review room'. The user has provided a topic, but more context is needed. Ask a clarifying question to understand what specific aspect of the topic they want to review. Your output must be in the specified JSON format."
            user_prompt = f"The topic is '{topic}'. The conversation history of the parent room does not seem to contain enough information about it. What clarifying question should I ask the user? Respond in JSON format with a single key 'question'."

            question_str, _ = await llm_service.invoke("openai", "gpt-4o", system_prompt, user_prompt, "question-gen", response_format="json")

            try:
                validated_data = LLMQuestionResponse.model_validate_json(question_str)
                question = validated_data.question
            except Exception as e:
                logger.error(f"Failed to validate question from LLM: {e}. Raw response: {question_str}")
                question = "죄송합니다. 주제에 대해 조금 더 자세히 설명해주시겠어요?" # Fallback question

            return CreateReviewRoomInteractiveResponse(status="needs_more_context", question=question)
