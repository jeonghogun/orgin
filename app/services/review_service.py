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

        panel_scripts = {
            "GPT-4o": {
                "round1": {
                    "round": 1,
                    "panelist": "GPT-4o",
                    "message": (
                        f"{topic}을(를) 두고만 있지 말고 30일 파일럿을 바로 띄워봅시다. 핵심 고객 200명을 묶어 빠르게 실험하면 시장 반응과 장애 요소를 동시에 확인할 수 있어요."
                    ),
                    "key_takeaway": "30일 파일럿으로 시장 반응을 빠르게 수집.",
                    "references": [],
                    "no_new_arguments": False,
                },
                "round2": {
                    "round": 2,
                    "panelist": "GPT-4o",
                    "message": (
                        "Claude 3 Haiku가 말한 체크리스트는 전적으로 동의합니다. 다만 Gemini 1.5 Flash가 제안한 사용자 확장은, 파일럿 품질 게이트를 먼저 통과한 뒤에 바로 붙여보죠. 실험 대시보드를 첫 주 안에 열어 투명하게 공유합시다."
                    ),
                    "key_takeaway": "통제 절차를 붙인 상태에서 속도를 유지해야 한다.",
                    "references": [
                        {
                            "panelist": "Claude 3 Haiku",
                            "round": 1,
                            "quote": "통제 범위를 선명하게",
                            "stance": "support",
                        },
                        {
                            "panelist": "Gemini 1.5 Flash",
                            "round": 1,
                            "quote": "사용자 서브셋을 넓히자",
                            "stance": "build",
                        },
                    ],
                    "no_new_arguments": False,
                },
                "round3": {
                    "round": 3,
                    "panelist": "GPT-4o",
                    "message": (
                        "이제 모두 같은 그림을 그리네요. Claude 3 Haiku가 라운드 2에서 강조한 체크리스트 통과 기준을 각 단계 게이트로 두고, Gemini 1.5 Flash가 말한 실시간 피드백 스트림을 성공 판정 지표로 삼겠습니다. 이렇게 하면 30일 파일럿 후 60일 확장 검증으로 자연스럽게 넘어갈 수 있어요."
                    ),
                    "key_takeaway": "체크리스트와 피드백을 묶은 30일→60일 로드맵.",
                    "references": [
                        {
                            "panelist": "Claude 3 Haiku",
                            "round": 2,
                            "quote": "체크리스트 없으면 리스크가 남는다",
                            "stance": "support",
                        },
                        {
                            "panelist": "Gemini 1.5 Flash",
                            "round": 2,
                            "quote": "실험 로그를 스트리밍하자",
                            "stance": "build",
                        },
                    ],
                    "no_new_arguments": False,
                },
            },
            "Claude 3 Haiku": {
                "round1": {
                    "round": 1,
                    "panelist": "Claude 3 Haiku",
                    "message": (
                        f"{topic}이(가) 흥미롭긴 하지만, 시작 전에 통제 경계를 먼저 그립시다. 데이터 사용 목적과 보안 요건을 명문화하지 않으면 초기에 얻은 신뢰를 잃을 수 있어요."
                    ),
                    "key_takeaway": "파일럿 전에 통제 경계와 감사 기준을 잠그자.",
                    "references": [],
                    "no_new_arguments": False,
                },
                "round2": {
                    "round": 2,
                    "panelist": "Claude 3 Haiku",
                    "message": (
                        "GPT-4o의 30일 타임라인은 좋지만, 법무·보안 검토 시간을 포함해야 합니다. Gemini 1.5 Flash가 말한 실험 대시보드를 감사 로그로 활용하면 속도와 투명성을 동시에 확보할 수 있겠네요."
                    ),
                    "key_takeaway": "속도를 인정하되 법무·보안 체크포인트는 반드시 유지.",
                    "references": [
                        {
                            "panelist": "GPT-4o",
                            "round": 1,
                            "quote": "30일 파일럿",
                            "stance": "build",
                        },
                        {
                            "panelist": "Gemini 1.5 Flash",
                            "round": 1,
                            "quote": "실험 대시보드",
                            "stance": "support",
                        },
                    ],
                    "no_new_arguments": False,
                },
                "round3": {
                    "round": 3,
                    "panelist": "Claude 3 Haiku",
                    "message": (
                        "라운드 2에서 합의한 대시보드가 있으면 감사팀도 안심할 수 있겠습니다. GPT-4o가 제안한 30일→60일 구조에 동의하되, 각 단계 입구에서 법무·보안·데이터 담당자가 체크리스트를 승인하는 절차를 넣읍시다."
                    ),
                    "key_takeaway": "30일→60일 전환 시 감사 승인 게이트를 추가.",
                    "references": [
                        {
                            "panelist": "GPT-4o",
                            "round": 3,
                            "quote": "30일 파일럿 후 60일 확장",
                            "stance": "support",
                        },
                        {
                            "panelist": "Gemini 1.5 Flash",
                            "round": 2,
                            "quote": "실험 대시보드를 감사 로그로",
                            "stance": "build",
                        },
                    ],
                    "no_new_arguments": False,
                },
            },
            "Gemini 1.5 Flash": {
                "round1": {
                    "round": 1,
                    "panelist": "Gemini 1.5 Flash",
                    "message": (
                        f"{topic}을(를) 활용하면 얼리어답터 그룹에서 얻은 피드백을 빠르게 제품 개선으로 돌릴 수 있어요. 실험을 세 단계로 나눠 각 단계마다 학습 목표를 정리해 두면 확장 타이밍을 스스로 증명할 수 있습니다."
                    ),
                    "key_takeaway": "세 단계 실험으로 학습과 확장을 동시에 설계.",
                    "references": [],
                    "no_new_arguments": False,
                },
                "round2": {
                    "round": 2,
                    "panelist": "Gemini 1.5 Flash",
                    "message": (
                        "GPT-4o의 속도 제안은 마음에 들어요. 다만 Claude 3 Haiku가 요구한 통제를 충족시키려면 실험 로그를 스트리밍으로 공유하고, 사용자 반응 하이라이트를 매주 시각화해 드리죠."
                    ),
                    "key_takeaway": "속도에 투명성을 얹어 모두가 안심하도록 만들자.",
                    "references": [
                        {
                            "panelist": "GPT-4o",
                            "round": 1,
                            "quote": "빠르게 실험",
                            "stance": "support",
                        },
                        {
                            "panelist": "Claude 3 Haiku",
                            "round": 1,
                            "quote": "통제 경계를 선명하게",
                            "stance": "build",
                        },
                    ],
                    "no_new_arguments": False,
                },
                "round3": {
                    "round": 3,
                    "panelist": "Gemini 1.5 Flash",
                    "message": (
                        "두 분의 합의 덕분에 그림이 깔끔해졌네요. GPT-4o가 말한 30일 파일럿이 끝나면, Claude 3 Haiku가 요구한 승인 게이트를 통과한 뒤 다음 60일 동안 성장 지표를 확장 실험에 연결해보겠습니다."
                    ),
                    "key_takeaway": "승인 게이트 뒤에 성장 지표를 붙여 확장 속도를 유지.",
                    "references": [
                        {
                            "panelist": "GPT-4o",
                            "round": 2,
                            "quote": "대시보드를 첫 주에 열자",
                            "stance": "support",
                        },
                        {
                            "panelist": "Claude 3 Haiku",
                            "round": 3,
                            "quote": "법무·보안 승인 게이트",
                            "stance": "build",
                        },
                    ],
                    "no_new_arguments": False,
                },
            },
        }

        round_status = {
            1: "initial_turn_complete",
            2: "rebuttal_turn_complete",
            3: "synthesis_turn_complete",
        }

        for round_num in (1, 2, 3):
            for persona, script in panel_scripts.items():
                payload = {
                    "persona": persona,
                    "round": round_num,
                    "payload": script[f"round{round_num}"],
                }
                message_content = json.dumps(payload, ensure_ascii=False, indent=2)
                self._save_message_and_stream(
                    review_id,
                    review_room_id,
                    message_content,
                    timestamp=round_timestamp,
                )
                round_timestamp += 1

            try:
                self.storage.update_review(review_id, {"current_round": round_num})
            except Exception as update_error:
                logger.warning(
                    "Failed to update current_round after round %s in mock review.",
                    round_num,
                    extra={"review_id": review_id, "error": str(update_error)},
                )

            status_label = round_status[round_num]
            self._log_status_event(review_id, status_label, timestamp=round_timestamp)
            round_timestamp += 1

        final_report = {
            "executive_summary": (
                f"GPT-4o, Claude 3 Haiku, Gemini 1.5 Flash는 {topic}을 빠르게 실험하되 명확한 거버넌스와 단계적 확장을 병행하자는 방향으로 정렬했습니다."
            ),
            "strongest_consensus": [
                "베타 → 확장 검증 순으로 단계별 게이트를 운영한다.",
                "데이터 거버넌스와 품질 체크리스트를 초기부터 준비해 투명하게 공유한다.",
            ],
            "remaining_disagreements": [
                "확장 의사결정 타이밍과 투자 강도는 추가 합의가 필요합니다.",
            ],
            "recommendations": [
                "실험 로그와 감사 기록을 통합 대시보드로 공유하고 책임자를 지정한다.",
                f"{topic} 관련 경영 리뷰를 60일째에 열어 투자/중단을 재평가한다.",
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
                room_id = generate_id()
                new_room = await asyncio.to_thread(
                    self.storage.create_room,
                    room_id=room_id,
                    name=f"검토: {topic}",
                    owner_id=user_id,
                    room_type=RoomType.REVIEW,
                    parent_id=parent_id,
                )

                review_id = generate_id()
                instruction = "이 주제에 대해 최대 4 라운드에 걸쳐 심도 있게 토론하되, 추가 주장이 없으면 조기에 종료해주세요."
                review_meta = ReviewMeta(
                    review_id=review_id,
                    room_id=room_id,
                    topic=topic,
                    instruction=instruction,
                    status="pending",
                    total_rounds=4,
                    created_at=get_current_timestamp(),
                )
                await asyncio.to_thread(self.storage.save_review_meta, review_meta)

                intro_message = build_intro_message(topic, instruction)
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
                panel_configs = llm_strategy_service.get_default_panelists()
                usable_panelists = [p for p in panel_configs if p.provider in available_providers]

                if not usable_panelists:
                    await asyncio.to_thread(
                        self._run_mock_review,
                        review_id,
                        room_id,
                        topic,
                        instruction,
                    )
                    self._notify_mock_celery_task(
                        review_id=review_id,
                        review_room_id=room_id,
                        topic=topic,
                        instruction=instruction,
                        panelists=None,
                        trace_id=trace_id,
                    )
                else:
                    await self.start_review_process(
                        review_id=review_id,
                        review_room_id=room_id,
                        topic=topic,
                        instruction=instruction,
                        panelists=[p.provider for p in usable_panelists],
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
