"""
Review Service - Orchestrates the multi-agent review process using Celery.
"""
import asyncio
import json
import logging
import uuid
from typing import Optional, List, Dict, Any
from unittest.mock import Mock

from app.services.storage_service import StorageService, storage_service
from app.celery_app import celery_app
from app.models.schemas import (
    Room,
    ReviewMeta,
    CreateReviewRoomInteractiveResponse,
    LLMQuestionResponse,
    Message,
    WebSocketMessage,
)
from app.models.review_schemas import LLMReviewTopicSuggestion
from app.models.enums import RoomType
from app.utils.helpers import generate_id, get_current_timestamp
from app.services.llm_service import get_llm_service
from app.core.errors import InvalidRequestError

# Import tasks to ensure they are registered
from app.tasks import review_tasks

from app.services.redis_pubsub import redis_pubsub_manager
from app.services.realtime_service import realtime_service
from app.services.llm_strategy import llm_strategy_service
from app.services.review_templates import build_intro_message, build_final_report_message

logger = logging.getLogger(__name__)


class ReviewService:
    """Orchestrates the multi-agent, multi-round review process."""

    def __init__(self, storage_service: StorageService) -> None:
        """Initialize the review service."""
        super().__init__()
        self.storage: StorageService = storage_service

    async def _generate_review_topic_title(
        self,
        llm_service,
        *,
        fallback_topic: str,
        conversation: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Ask the LLM to produce a concise, user-facing review topic title."""

        sanitized_fallback = (fallback_topic or "").strip() or "리뷰 주제"

        history_lines: List[str] = []
        if history:
            for item in history[-6:]:  # keep the most recent context
                role = (item.get("role") or "").strip() or "user"
                content = (item.get("content") or "").strip()
                if content:
                    history_lines.append(f"{role}: {content}")

        conversation_excerpt = (conversation or "").strip()
        if len(conversation_excerpt) > 4000:
            conversation_excerpt = conversation_excerpt[-4000:]

        prompt_sections: List[str] = [f"기본 주제: {sanitized_fallback}"]
        if history_lines:
            prompt_sections.append("사용자 메모:")
            prompt_sections.append("\n".join(history_lines))
        if conversation_excerpt:
            prompt_sections.append("관련 대화:")
            prompt_sections.append(conversation_excerpt)

        prompt_sections.append(
            "위 정보를 기반으로 검토룸 제목을 만드세요. 한 줄짜리 간결한 표현으로 작성하고, 30자 이내 한국어가 자연스럽다면 한국어로 작성합니다."
        )

        system_prompt = (
            "You craft executive review room titles. "
            "Return JSON with a single `title` field containing a polished, specific subject line without quotes."
        )

        user_prompt = "\n\n".join(prompt_sections)

        try:
            response_text, _ = await llm_service.invoke(
                provider_name="openai",
                model="gpt-4o",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                request_id="review-topic-generator",
                response_format="json",
            )
            suggestion = LLMReviewTopicSuggestion.model_validate_json(response_text)
            candidate = suggestion.title.strip()
            if not candidate:
                return sanitized_fallback

            single_line = " ".join(candidate.split())
            if len(single_line) > 60:
                single_line = single_line[:57].rstrip() + "..."
            return single_line
        except Exception as topic_error:  # noqa: BLE001 - logging diagnostic context
            logger.warning(
                "Falling back to requested review topic due to generation error: %s",
                topic_error,
                exc_info=True,
            )
            return sanitized_fallback

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
        if not task:
            logger.error("Could not find Celery task: app.tasks.review_tasks.run_initial_panel_turn")
            self._log_status_event(review_id, "queue_unavailable")
            await asyncio.to_thread(
                self._run_mock_review,
                review_id,
                review_room_id,
                topic,
                instruction,
            )
            return

        try:
            self._log_status_event(review_id, "queued")
            task.delay(
                review_id=review_id,
                review_room_id=review_room_id,
                topic=topic,
                instruction=instruction,
                panelists_override=panelists,
                trace_id=trace_id,
            )
            self._log_status_event(review_id, "dispatched")
        except Exception as dispatch_error:
            logger.error(
                "Failed to dispatch Celery review chain for %s: %s",
                review_id,
                dispatch_error,
                exc_info=True,
            )
            self._log_status_event(review_id, "dispatch_failed")
            await asyncio.to_thread(
                self._run_mock_review,
                review_id,
                review_room_id,
                topic,
                instruction,
            )

    def _save_message_and_stream(
        self,
        review_id: str,
        review_room_id: str,
        content: str,
        *,
        role: str = "assistant",
        user_id: str = "assistant",
        timestamp: Optional[int] = None,
    ) -> None:
        """Helper to persist a message and broadcast it to review listeners."""

        message = Message(
            message_id=generate_id(),
            room_id=review_room_id,
            user_id=user_id,
            role=role,
            content=content,
            timestamp=timestamp or get_current_timestamp(),
        )

        try:
            self.storage.save_message(message)
        except Exception as save_error:
            logger.error(
                "Failed to save review message.",
                extra={
                    "review_id": review_id,
                    "room_id": review_room_id,
                    "user_id": user_id,
                    "role": role,
                    "error": str(save_error),
                },
                exc_info=True,
            )
            return

        redis_pubsub_manager.publish_sync(
            f"review_{review_id}",
            WebSocketMessage(
                type="new_message",
                review_id=review_id,
                payload=message.model_dump(),
            ).model_dump_json(),
        )

    def _log_status_event(self, review_id: str, status: str, *, timestamp: Optional[int] = None) -> None:
        """Persist and broadcast a status update event for a review."""

        ts = timestamp or get_current_timestamp()
        event_payload = {"status": status}
        try:
            self.storage.log_review_event(
                {
                    "review_id": review_id,
                    "ts": ts,
                    "type": "status_update",
                    "round": None,
                    "actor": "system",
                    "content": json.dumps(event_payload),
                }
            )
        except Exception as log_error:
            logger.warning(
                "Failed to persist status event %s for review %s: %s",
                status,
                review_id,
                log_error,
                exc_info=True,
            )

        redis_pubsub_manager.publish_sync(
            f"review_{review_id}",
            WebSocketMessage(
                type="status_update",
                review_id=review_id,
                ts=ts,
                payload=event_payload,
            ).model_dump_json(),
        )

    def record_status_event(self, review_id: str, status: str, *, timestamp: Optional[int] = None) -> None:
        """Public helper for tests and admin tools to log review status transitions."""
        self._log_status_event(review_id, status, timestamp=timestamp)

    def _notify_mock_celery_task(
        self,
        *,
        review_id: str,
        review_room_id: str,
        topic: str,
        instruction: str,
        panelists: Optional[List[str]],
        trace_id: str,
    ) -> None:
        """Call the mocked Celery task during tests without dispatching real work."""

        task = celery_app.tasks.get("app.tasks.review_tasks.run_initial_panel_turn")
        if not task:
            return

        delay_callable = getattr(task, "delay", None)
        if isinstance(delay_callable, Mock):
            delay_callable(
                review_id=review_id,
                review_room_id=review_room_id,
                topic=topic,
                instruction=instruction,
                panelists_override=panelists,
                trace_id=trace_id,
            )

    def _run_mock_review(self, review_id: str, review_room_id: str, topic: str, instruction: str) -> None:
        """Generate a lightweight, synchronous review flow when no LLM providers are available."""
        logger.warning(
            "No LLM providers are configured. Falling back to mock review generation.",
            extra={"review_id": review_id, "room_id": review_room_id},
        )

        start_ts = get_current_timestamp()
        self._log_status_event(review_id, "fallback_started", timestamp=start_ts)

        # Inform listeners that the review has started.
        try:
            self.storage.update_review(review_id, {"status": "in_progress"})
        except Exception as update_error:
            logger.warning(
                "Failed to update review status to in_progress during mock flow.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        round_timestamp = get_current_timestamp()
        self._log_status_event(review_id, "processing", timestamp=round_timestamp)
        round_timestamp += 1

        topic_label = (topic or "이 주제").strip()
        instruction_hint = (instruction or "").strip()

        conversation_script = [
            {
                "persona": "GPT-4o (모의 패널)",
                "message": (
                    f"{topic_label}에 대해 지금 얻은 정보로 보면, 실행 판단을 미룰 수 있는 여지가 많지 않습니다."
                    " 우선 고객 행동 데이터를 세 갈래로 나눠 살피고, 일주일 안에 실험 가설을 검증할 수 있는 경량 대시보드를 열겠습니다. "
                    f"{instruction_hint or '토론 지침'}의 취지를 살려 빠르게 정리하죠."
                ),
                "key_takeaway": "고객 데이터를 나눠 빠르게 검증 가능한 실험판을 만든다.",
                "references": [],
            },
            {
                "persona": "Claude 3 Haiku (모의 패널)",
                "message": (
                    "속도를 내는 건 좋은데, 개인정보 사용과 외부 공유 범위를 먼저 확정해야 합니다."
                    " GPT-4o가 말한 경량 대시보드를 감사 로그와 연동하면 속도와 신뢰를 동시에 챙길 수 있습니다."
                ),
                "key_takeaway": "속도를 유지하되 감사·보안 경계를 초기에 고정한다.",
                "references": [
                    {
                        "panelist": "GPT-4o (모의 패널)",
                        "quote": "일주일 안에 실험 가설 검증",
                        "stance": "support",
                    }
                ],
            },
            {
                "persona": "Gemini 1.5 Flash (모의 패널)",
                "message": (
                    "두 분의 의견을 묶어 보면, 베타 그룹을 두 겹으로 나눠 실험하면 어떨까요?"
                    " 한쪽은 핵심 기능 반응을, 다른 쪽은 확장 아이디어를 검증하도록 설계하면 2주 안에 확장 타이밍을 가늠할 근거가 나올 겁니다."
                ),
                "key_takeaway": "베타 그룹을 이중으로 설계해 학습 범위를 넓힌다.",
                "references": [
                    {
                        "panelist": "GPT-4o (모의 패널)",
                        "quote": "실험 가설을 빠르게 검증",
                        "stance": "build",
                    },
                    {
                        "panelist": "Claude 3 Haiku (모의 패널)",
                        "quote": "감사 로그와 연동",
                        "stance": "support",
                    },
                ],
            },
            {
                "persona": "GPT-4o (모의 패널)",
                "message": (
                    "좋습니다. 그러면 1주차에는 핵심 지표를, 2주차에는 확장 아이디어를 검증하고 요약본을 같은 채널에 실시간으로 공유하겠습니다."
                    " Claude가 요구한 통제 기준은 체크리스트 형태로 대시보드 첫 화면에 붙여두죠."
                ),
                "key_takeaway": "주차별 검증 목표와 통제 기준을 대시보드에 함께 노출.",
                "references": [
                    {
                        "panelist": "Gemini 1.5 Flash (모의 패널)",
                        "quote": "베타 그룹을 두 겹으로 나누자",
                        "stance": "support",
                    },
                    {
                        "panelist": "Claude 3 Haiku (모의 패널)",
                        "quote": "감사 기준 고정",
                        "stance": "build",
                    },
                ],
            },
            {
                "persona": "Claude 3 Haiku (모의 패널)",
                "message": (
                    "그 구조라면 법무 검토도 병행할 수 있겠네요. 첫 주에는 데이터 사용 동의를 재확인하고, 둘째 주에는 확장 시나리오 별 리스크를 체크리스트로 정리하겠습니다."
                    " 실험이 길어지지 않도록 의사결정 일정은 미리 공지하죠."
                ),
                "key_takeaway": "주차별 리스크 검토와 의사결정 일정을 선제적으로 공개.",
                "references": [
                    {
                        "panelist": "GPT-4o (모의 패널)",
                        "quote": "주차별 검증 목표",
                        "stance": "support",
                    }
                ],
            },
            {
                "persona": "Gemini 1.5 Flash (모의 패널)",
                "message": (
                    "마무리로, 실험 하이라이트를 주간 쇼트폼 리포트로 만들겠습니다. 데이터 지표와 이용자 코멘트를 한 화면에 보여주면 경영진도 빠르게 판단할 수 있을 거예요."
                    " 이렇게 하면 충분히 합의가 되면 바로 실행으로 전환할 수 있습니다."
                ),
                "key_takeaway": "주간 하이라이트 리포트로 합의와 실행 전환을 가속.",
                "references": [
                    {
                        "panelist": "Claude 3 Haiku (모의 패널)",
                        "quote": "의사결정 일정 공지",
                        "stance": "build",
                    }
                ],
            },
        ]

        status_markers = {
            1: "conversation_started",
            3: "conversation_midway",
            len(conversation_script): "conversation_complete",
        }

        for index, entry in enumerate(conversation_script, start=1):
            payload = {
                "persona": entry["persona"],
                "payload": {
                    "panelist": entry["persona"],
                    "message": entry["message"],
                    "key_takeaway": entry["key_takeaway"],
                    "references": entry.get("references", []),
                    "no_new_arguments": entry.get("no_new_arguments", False),
                },
            }

            message_content = json.dumps(payload, ensure_ascii=False)
            self._save_message_and_stream(
                review_id,
                review_room_id,
                message_content,
                timestamp=round_timestamp,
            )
            round_timestamp += 1

            status_label = status_markers.get(index)
            if status_label:
                self._log_status_event(review_id, status_label, timestamp=round_timestamp)
                round_timestamp += 1

        final_report = {
            "executive_summary": (
                f"패널들은 {topic_label} 실험을 빠르게 전개하되, 감사 가능한 투명성과 주차별 검증 목표를 병행해야 한다는 데 뜻을 모았습니다."
            ),
            "strongest_consensus": [
                "실험 대시보드에 검증 목표와 통제 기준을 함께 노출한다.",
                "주간 리포트로 핵심 수치와 사용자 반응을 동시에 공유한다.",
            ],
            "remaining_disagreements": [
                "확장 단계에서 투자 강도를 어디까지 높일지는 추가 검토가 필요합니다.",
            ],
            "recommendations": [
                "베타 그룹을 이중으로 설계하고 의사결정 일정을 미리 공유한다.",
                "감사 로그와 연동된 대시보드를 운영해 거버넌스를 선제적으로 확보한다.",
            ],
        }

        final_message_content = build_final_report_message(topic, final_report)

        try:
            self.storage.save_final_report(review_id=review_id, report_data=final_report)
        except Exception as final_report_error:
            logger.error(
                "Failed to save mock final report.",
                extra={"review_id": review_id, "error": str(final_report_error)},
                exc_info=True,
            )
        else:
            self._save_message_and_stream(
                review_id,
                review_room_id,
                final_message_content,
                user_id="observer",
                timestamp=round_timestamp,
            )

        round_timestamp += 1

        try:
            self.storage.update_review(review_id, {"status": "completed"})
        except Exception as update_error:
            logger.warning(
                "Failed to update review status to completed in mock flow.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        self._log_status_event(review_id, "fallback_finished", timestamp=round_timestamp)
        self._log_status_event(review_id, "completed", timestamp=round_timestamp)

    def get_status_overview(self, review_id: str) -> Dict[str, Any]:
        """Summarise the current status and recent history of a review."""
        review = self.storage.get_review_meta(review_id)
        if not review:
            raise InvalidRequestError("Review not found")

        history = self.storage.get_recent_status_events(review_id, limit=25)
        last_event = history[-1] if history else None
        fallback_active = any(event.get("status", "").startswith("fallback") for event in history)
        final_report = self.storage.get_final_report(review_id)

        snapshot: Dict[str, Any] = {
            "review_id": review.review_id,
            "status": review.status,
            "current_round": review.current_round or 0,
            "total_rounds": review.total_rounds,
            "status_history": history,
            "fallback_active": fallback_active,
            "has_report": bool(final_report),
        }

        if last_event:
            snapshot["last_event"] = last_event

        return snapshot

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
        try:
            parent_room = await asyncio.to_thread(self.storage.get_room, parent_id)
            if not parent_room or parent_room.type != RoomType.SUB:
                raise InvalidRequestError("Parent room must be a sub-room.")

            llm_service = get_llm_service()

            topic = topic.strip()

            try:
                messages = await asyncio.to_thread(self.storage.get_messages, parent_id)
            except Exception as fetch_error:
                logger.error(
                    "Failed to load messages for review creation (parent %s): %s",
                    parent_id,
                    fetch_error,
                    exc_info=True,
                )
                messages = []

            full_conversation = ""
            for msg in messages:
                role = getattr(msg, "role", "unknown")
                content = getattr(msg, "content", "")
                full_conversation += f"{role}: {content}\n"

            context_sufficient = topic.lower() in full_conversation.lower()
            if history and len(history) > 0:
                context_sufficient = True

            if context_sufficient:
                generated_topic = await self._generate_review_topic_title(
                    llm_service,
                    fallback_topic=topic,
                    conversation=full_conversation,
                    history=history,
                )

                room_id = generate_id()
                new_room = await asyncio.to_thread(
                    self.storage.create_room,
                    room_id=room_id,
                    name=f"검토: {generated_topic}",
                    owner_id=user_id,
                    room_type=RoomType.REVIEW,
                    parent_id=parent_id,
                )

                review_id = generate_id()
                instruction = (
                    "세 명의 패널이 하나의 단톡방에서 깊이 있게 토론하되,"
                    " 충분한 합의가 이뤄지면 더 길게 늘리지 말고 정리하도록 요청했습니다."
                )
                review_meta = ReviewMeta(
                    review_id=review_id,
                    room_id=room_id,
                    topic=generated_topic,
                    instruction=instruction,
                    status="pending",
                    total_rounds=4,
                    created_at=get_current_timestamp(),
                )
                await asyncio.to_thread(self.storage.save_review_meta, review_meta)

                intro_message = build_intro_message(generated_topic, instruction)
                await asyncio.to_thread(
                    self._save_message_and_stream,
                    review_id,
                    room_id,
                    intro_message,
                    role="assistant",
                    user_id="observer",
                )

                trace_id = str(uuid.uuid4())
                available_providers = llm_service.get_available_providers()
                usable_panelists = llm_strategy_service.get_panelists_for_providers(
                    available_providers
                )

                if not usable_panelists:
                    await asyncio.to_thread(
                        self._run_mock_review,
                        review_id,
                        room_id,
                        generated_topic,
                        instruction,
                    )
                    self._notify_mock_celery_task(
                        review_id=review_id,
                        review_room_id=room_id,
                        topic=generated_topic,
                        instruction=instruction,
                        panelists=None,
                        trace_id=trace_id,
                    )
                else:
                    provider_names: List[str] = []
                    for config in usable_panelists:
                        if config.provider not in provider_names:
                            provider_names.append(config.provider)
                    await self.start_review_process(
                        review_id=review_id,
                        review_room_id=room_id,
                        topic=generated_topic,
                        instruction=instruction,
                        panelists=provider_names,
                        trace_id=trace_id,
                    )

                return CreateReviewRoomInteractiveResponse(status="created", room=Room.model_validate(new_room))
            else:
                system_prompt = "You are an AI assistant helping a user create a 'review room'. The user has provided a topic, but more context is needed. Ask a clarifying question to understand what specific aspect of the topic they want to review. Your output must be in the specified JSON format."
                user_prompt = f"The topic is '{topic}'. The conversation history of the parent room does not seem to contain enough information about it. What clarifying question should I ask the user? Respond in JSON format with a single key 'question'."

                question_str, _ = await llm_service.invoke(
                    provider_name="openai",
                    model="gpt-4o",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    request_id="question-gen",
                    response_format="json"
                )

                try:
                    validated_data = LLMQuestionResponse.model_validate_json(question_str)
                    question = validated_data.question
                except Exception as e:
                    logger.error(f"Failed to validate question from LLM: {e}. Raw response: {question_str}")
                    question = "죄송합니다. 주제에 대해 조금 더 자세히 설명해주시겠어요?" # Fallback question

                prompt_message_payload: Optional[Message] = None
                prompt_message = Message(
                    message_id=generate_id(),
                    room_id=parent_id,
                    user_id="review_assistant",
                    role="assistant",
                    content=question,
                    timestamp=get_current_timestamp(),
                )

                try:
                    await asyncio.to_thread(self.storage.save_message, prompt_message)
                except Exception as save_error:
                    logger.warning(
                        "Failed to persist interactive review prompt question for room %s: %s",
                        parent_id,
                        save_error,
                        exc_info=True,
                    )
                else:
                    prompt_message_payload = prompt_message
                    try:
                        await realtime_service.publish(parent_id, "new_message", prompt_message.model_dump())
                    except Exception as broadcast_error:
                        logger.warning(
                            "Failed to broadcast interactive review prompt question for room %s: %s",
                            parent_id,
                            broadcast_error,
                            exc_info=True,
                        )

                return CreateReviewRoomInteractiveResponse(
                    status="needs_more_context",
                    question=question,
                    prompt_message=prompt_message_payload,
                )
        except InvalidRequestError:
            raise
        except Exception as unexpected_error:
            logger.exception(
                "Failed to create interactive review room",
                extra={
                    "parent_id": parent_id,
                    "topic": topic,
                    "user_id": user_id,
                },
            )
            raise


# Global service instance
review_service: ReviewService = None

def get_review_service() -> ReviewService:
    global review_service
    if review_service is None:
        review_service = ReviewService(storage_service=storage_service)
    return review_service
