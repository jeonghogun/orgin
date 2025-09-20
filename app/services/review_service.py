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
                    "key_takeaway": (
                        f"{topic}은/는 빠른 실험으로 시장 반응을 학습할 기회입니다. 단, 품질 안전망을 같이 준비해야 합니다."
                    ),
                    "arguments": [
                        "초기 4주 동안 제한된 고객군과 베타 테스트를 운영하면 실사용 데이터를 확보할 수 있습니다.",
                        "수집된 데이터로 ROI 가설과 운영 지표를 설정하면 의사결정 속도를 높일 수 있습니다.",
                    ],
                    "risks": [
                        "품질 기준이 모호하면 베타 단계에서 부정적 피드백이 확대될 수 있습니다.",
                        "조직의 우선순위가 분산되면 실험 속도가 둔화될 위험이 있습니다.",
                    ],
                    "opportunities": [
                        "시장 반응을 조기에 확인해 경쟁사 대비 학습 곡선을 앞당길 수 있습니다.",
                        "크로스펑셔널 팀이 협업하면서 실험 문화가 강화됩니다.",
                    ],
                },
                "round2": {
                    "round": 2,
                    "no_new_arguments": False,
                    "agreements": [
                        "Claude 3 Haiku가 말한 “데이터 거버넌스 확보”는 베타 런칭 전에 반드시 맞춰야 합니다."
                    ],
                    "disagreements": [
                        {
                            "point": "Gemini 1.5 Flash의 “장기 합의가 필요하다”는 우려를 너무 오래 끌면 모멘텀을 잃을 수 있습니다.",
                            "reasoning": "의사결정 창을 30일 이내로 제한하고, 미해결 쟁점은 별도 워킹그룹에서 병행 처리해야 속도를 유지할 수 있습니다.",
                        }
                    ],
                    "additions": [
                        {
                            "point": "실험 로그를 실시간으로 리뷰할 수 있는 대시보드를 출범 주간에 준비합시다.",
                            "reasoning": "데이터를 투명하게 공유해야 Skeptic 관점의 검증 요구와 속도 요구를 동시에 충족할 수 있습니다.",
                        }
                    ],
                },
                "round3": {
                    "round": 3,
                    "no_new_arguments": False,
                    "executive_summary": "세 모델 모두 “빠른 실험”과 “통제된 확장”에 공감했습니다. GPT-4o는 실행 속도를, Claude 3 Haiku는 위험 관리 절차를, Gemini 1.5 Flash는 단계적 확장 전략을 강조했습니다.",
                    "conclusion": (
                        f"{topic}을(를) 30일 베타 → 60일 확장 검증으로 나누고, 매 단계마다 품질 게이트와 ROI 검토를 병행하면 현실적인 균형을 만들 수 있습니다."
                    ),
                    "recommendations": [
                        "베타 시작 전에 공통 대시보드와 품질 체크리스트를 확정한다.",
                        "주차별 리스크 리뷰 세션에 세 모델이 합의한 담당자를 지정한다.",
                        "60일째에 투자/중단 결정을 위한 경영 리뷰를 예약한다.",
                    ],
                },
            },
            "Claude 3 Haiku": {
                "round1": {
                    "round": 1,
                    "key_takeaway": (
                        f"{topic}은 매력적이지만, 시작 전에 통제 범위와 리스크 대응 계획을 선명하게 해야 합니다."
                    ),
                    "arguments": [
                        "법적·보안 요건을 명확히 검토하지 않으면 베타 단계에서 바로 제동이 걸릴 수 있습니다.",
                        "ROI 가설을 선제적으로 준비해야 경영진 설득과 후속 투자 논의가 수월합니다.",
                    ],
                    "risks": [
                        "규제 요구사항 누락으로 출시 일정이 미뤄질 수 있습니다.",
                        "장기간 실험이 이어지면 조직 피로도가 커질 수 있습니다.",
                    ],
                    "opportunities": [
                        "사전 통제를 준비하면 실패 비용을 크게 줄일 수 있습니다.",
                        "구축한 거버넌스 체계는 다른 프로젝트에도 재사용할 수 있습니다.",
                    ],
                },
                "round2": {
                    "round": 2,
                    "no_new_arguments": False,
                    "agreements": [
                        "GPT-4o가 강조한 “실제 사용자 데이터로 학습한다”는 접근은 설득력 있습니다."
                    ],
                    "disagreements": [
                        {
                            "point": "“30일 내 의사결정”만으로는 법무·보안 검토 시간을 확보하기 어렵습니다.",
                            "reasoning": "중간 게이트와 필수 체크리스트를 통과해야 다음 단계로 넘어가도록 합시다.",
                        }
                    ],
                    "additions": [
                        {
                            "point": "감사 로그와 데이터 사용 목적을 초기부터 문서화합시다.",
                            "reasoning": "Gemini 1.5 Flash가 지적한 조직 정렬 문제를 해결하고, 향후 감사 대응에도 도움이 됩니다.",
                        }
                    ],
                },
                "round3": {
                    "round": 3,
                    "no_new_arguments": False,
                    "executive_summary": "Claude 3 Haiku는 “속도와 통제의 균형”을 강조하며 GPT-4o의 실험 드라이브와 Gemini 1.5 Flash의 단계적 확장 제안을 조화시켰습니다.",
                    "conclusion": (
                        f"파일럿을 제한된 데이터와 명확한 KPI로 시작하고, 각 단계마다 법무·보안 검토를 완료한 뒤 확장하도록 운영하면 {topic}의 기대 효과와 리스크를 동시에 관리할 수 있습니다."
                    ),
                    "recommendations": [
                        "각 단계별 필수 체크리스트와 승인 권한을 문서화해 공유한다.",
                        "보안·법무 검토 일정과 실험 일정이 충돌하지 않도록 통합 캘린더를 운영한다.",
                        "리스크 대응 로그를 주 단위로 관찰자에게 보고한다.",
                    ],
                },
            },
            "Gemini 1.5 Flash": {
                "round1": {
                    "round": 1,
                    "key_takeaway": (
                        f"{topic}을(를) 현실적으로 추진하려면 단계별 합의와 명확한 커뮤니케이션 구조가 필요합니다."
                    ),
                    "arguments": [
                        "초기 파일럿 범위를 좁게 설정해 학습과 리스크를 동시에 관리해야 합니다.",
                        "관계자별 역할과 책임(RACI)을 명확히 하지 않으면 실행이 느려집니다.",
                    ],
                    "risks": [
                        "내부 합의 없이 확장하면 프로젝트가 중도에 멈출 수 있습니다.",
                        "과도한 문서화는 민첩성을 떨어뜨릴 수 있으므로 최소한의 형식만 유지해야 합니다.",
                    ],
                    "opportunities": [
                        "단계별 학습을 구조화하면 조직 전체의 실행력을 높일 수 있습니다.",
                        "획득한 인사이트를 다른 팀에도 공유해 레버리지를 만들 수 있습니다.",
                    ],
                },
                "round2": {
                    "round": 2,
                    "no_new_arguments": False,
                    "agreements": [
                        "GPT-4o가 제안한 “실험 데이터를 빠르게 공유”한다는 원칙은 협업에 도움이 됩니다.",
                        "Claude 3 Haiku의 “감사 로그 문서화” 요구는 장기적으로 조직 신뢰를 높입니다."
                    ],
                    "disagreements": [
                        {
                            "point": "GPT-4o의 “모든 미합의 쟁점을 30일 안에 해결하자”는 제안은 현실적으로 버겁습니다.",
                            "reasoning": "핵심 의사결정은 30일 안에 두되, 복잡한 항목은 병렬 워킹그룹으로 넘기는 완충 장치가 필요합니다.",
                        }
                    ],
                    "additions": [
                        {
                            "point": "라운드마다 관찰자에게 요약 브리핑을 제공합시다.",
                            "reasoning": "공유된 맥락이 있어야 결정 지연을 줄이고 팀 몰입감을 유지할 수 있습니다.",
                        }
                    ],
                },
                "round3": {
                    "round": 3,
                    "no_new_arguments": False,
                    "executive_summary": "Gemini 1.5 Flash는 두 모델의 논리를 종합해 “실험 속도를 유지하되 투명한 합의 구조로 리스크를 관리하자”는 결론을 제시합니다.",
                    "conclusion": (
                        f"{topic} 추진은 베타 단계, 확장 검증, 전사 확산의 세 구간으로 나누고 각 구간마다 명확한 합의 지점과 커뮤니케이션 리듬을 정의할 때 성공 확률이 높습니다."
                    ),
                    "recommendations": [
                        "RACI 매트릭스를 업데이트해 각 단계 책임자를 명확히 한다.",
                        "주요 결정 사항과 데이터 인사이트를 주차별 노트로 남겨 향후 리뷰에 활용한다.",
                        "확장 단계 전에 추가 리소스와 예산 확보 계획을 검토한다.",
                    ],
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
