"""
Review Service - Orchestrates the multi-agent review process using Celery.
"""
import asyncio
import logging
import uuid
from typing import Optional, List, Dict, Any

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
from app.api.dependencies import get_llm_service
from app.core.errors import InvalidRequestError

# Import tasks to ensure they are registered
from app.tasks import review_tasks

from app.services.redis_pubsub import redis_pubsub_manager
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

    def _run_mock_review(self, review_id: str, review_room_id: str, topic: str, instruction: str) -> None:
        """Generate a lightweight, synchronous review flow when no LLM providers are available."""
        logger.warning(
            "No LLM providers are configured. Falling back to mock review generation.",
            extra={"review_id": review_id, "room_id": review_room_id},
        )

        # Inform listeners that the review has started.
        try:
            self.storage.update_review(review_id, {"status": "in_progress"})
        except Exception as update_error:
            logger.warning(
                "Failed to update review status to in_progress during mock flow.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        redis_pubsub_manager.publish_sync(
            f"review_{review_id}",
            WebSocketMessage(
                type="status_update",
                review_id=review_id,
                payload={"status": "in_progress"},
            ).model_dump_json(),
        )

        round_timestamp = get_current_timestamp()

        panel_scripts = {
            "AGI Optimist": {
                "tagline": "희망적인 시각",
                "round1": {
                    "summary": (
                        f"{topic} 은/는 과감히 추진할 경우 시장 선점을 노릴 수 있는 기회입니다. "
                        "핵심은 실험을 빠르게 반복하면서 학습 곡선을 가파르게 만드는 데 있습니다."
                    ),
                    "bullets": [
                        "학습과 배포 주기를 짧게 가져가면 사용자의 반응을 즉시 반영할 수 있습니다.",
                        "초기에는 품질 지표보다 유저 유입과 활용 시나리오 발굴을 우선순위로 설정하세요.",
                    ],
                    "risks": [
                        "조직이 실험 속도를 따라가지 못하면 기대 성과가 지연될 수 있습니다.",
                        "과감한 투자로 인해 예산 소진이 빨라질 수 있으므로 성과 지표를 미리 합의해야 합니다.",
                    ],
                    "opportunities": [
                        "빠른 실험 문화는 팀 전반의 혁신 역량을 끌어올립니다.",
                        f"{topic} 관련 외부 파트너십을 조기에 확보할 수 있습니다.",
                    ],
                },
                "round2": {
                    "ack": [
                        "AGI Skeptic 요약에서 강조한 보안·품질 이슈는 반드시 초기 점검 리스트로 포함해야 합니다.",
                        "AGI Neutralist 의 단계적 전개 전략은 확장 시 리스크를 줄이는 데 도움됩니다.",
                    ],
                    "disagree": [
                        "과도한 위험 회피는 혁신 속도를 떨어뜨릴 수 있으니, 핵심 실험은 지연 없이 진행해야 합니다.",
                    ],
                    "additions": [
                        "지표 체계를 '실험 성공률'과 '사용자 반응 속도'로 이원화해 균형을 맞추겠습니다.",
                        f"{topic} 실험 결과를 주 1회 공유하여 빠른 의사결정이 가능하도록 하겠습니다.",
                    ],
                },
                "round3": {
                    "summary": (
                        f"실험 속도를 유지하되 Skeptic 과 Neutralist 가 제안한 통제 장치를 함께 도입하면 "
                        f"{topic} 의 가치를 빠르게 검증할 수 있습니다."
                    ),
                    "conclusion": (
                        f"파일럿 범위에서 명확한 성공 지표를 정의하고, 실험-피드백 루프를 자동화하십시오. "
                        "동시에 보안/품질 게이트를 두어 실패 가능성을 관리하면, 성장과 안정성을 모두 확보할 수 있습니다."
                    ),
                    "recommendations": [
                        "2주 단위 실험 사이클과 리뷰 미팅을 고정 일정으로 운영합니다.",
                        f"{topic} 관련 사용자 행동 로그를 정량적으로 수집·분석하는 대시보드를 구축합니다.",
                    ],
                },
            },
            "AGI Skeptic": {
                "tagline": "신중한 시각",
                "round1": {
                    "summary": (
                        f"{topic} 는 기대만큼이나 잠재 리스크가 많은 주제입니다. "
                        "추진 전에 통제할 수 있는 장치가 마련되어야 합니다."
                    ),
                    "bullets": [
                        "데이터 품질과 거버넌스를 먼저 진단해야 이후 문제를 줄일 수 있습니다.",
                        f"{topic} 에 대한 명확한 ROI 가 없다면 이사회 설득이 어렵습니다.",
                    ],
                    "risks": [
                        "규제 이슈가 발생하면 프로젝트 중단 가능성이 있습니다.",
                        "실험이 장기화될 경우 조직 피로도가 쌓입니다.",
                    ],
                    "opportunities": [
                        "사전에 리스크를 통제하면 실패 비용을 크게 줄일 수 있습니다.",
                        f"{topic} 의 실효성을 조기에 검증하면 향후 투자를 합리화할 수 있습니다.",
                    ],
                },
                "round2": {
                    "ack": [
                        "Optimist 의 빠른 실험 제안은 학습 속도를 높이는 좋은 접근입니다.",
                        "Neutralist 가 강조한 단계적 확장은 통제 가능한 범위를 유지하는 데 도움이 됩니다.",
                    ],
                    "disagree": [
                        "Optimist 가 제시한 대담한 투자 속도는 통제 장치가 준비되기 전에는 위험합니다.",
                    ],
                    "additions": [
                        "모든 실험에는 사전 승인된 데이터와 KPI 를 명시한 체크리스트가 필요합니다.",
                        f"{topic} 검증 단계마다 리스크 평가 리포트를 관찰자에게 제출하겠습니다.",
                    ],
                },
                "round3": {
                    "summary": (
                        f"실험을 진행하되 명확한 게이트와 감사 절차를 병행해야 {topic} 의 성공 가능성을 높일 수 있습니다."
                    ),
                    "conclusion": (
                        "초기에는 통제 가능한 소규모 데이터 세트로 검증을 수행하고, 각 단계마다 보안·컴플라이언스 검수를 "
                        "마쳐야 합니다. 이를 통해 실패 확률을 낮추고, 투자 대비 효과를 명확히 할 수 있습니다."
                    ),
                    "recommendations": [
                        "라운드마다 위험 평가 템플릿을 작성해 의사결정에 활용하세요.",
                        f"{topic} 관련 규제 대응 가이드를 사전에 준비해 돌발 상황에 대비하세요.",
                    ],
                },
            },
            "AGI Neutralist": {
                "tagline": "균형 잡힌 시각",
                "round1": {
                    "summary": (
                        f"{topic} 은/는 성장과 리스크 관리 모두를 요구하는 과제입니다. "
                        "두 관점을 조합해 단계별 로드맵을 설계해야 합니다."
                    ),
                    "bullets": [
                        "작은 파일럿으로 학습한 뒤 범위를 확장하는 것이 적절합니다.",
                        "조직 간 커뮤니케이션 구조를 정비하면 실행력이 높아집니다.",
                    ],
                    "risks": [
                        "내부 합의가 부족하면 추진 동력이 약해질 수 있습니다.",
                        "과도한 문서화는 민첩성을 떨어뜨릴 수 있습니다.",
                    ],
                    "opportunities": [
                        f"{topic} 추진 과정에서 팀 역량을 표준화할 수 있습니다.",
                        "학습된 인사이트를 다른 프로젝트에도 확장할 수 있습니다.",
                    ],
                },
                "round2": {
                    "ack": [
                        "Optimist 의 실험 가속 전략은 초기 동력을 만들기에 적합합니다.",
                        "Skeptic 의 체크리스트 제안은 품질 보증에 큰 도움이 됩니다.",
                    ],
                    "disagree": [
                        "양 극단의 주장만으로는 실행팀이 혼란스러울 수 있으니, 단계별 역할 정의가 필요합니다.",
                    ],
                    "additions": [
                        f"{topic} 추진을 위한 거버넌스 구조와 커뮤니케이션 채널을 명확히 하겠습니다.",
                        "라운드 종료마다 관찰자에게 핵심 결정 사항을 요약 보고해 투명성을 확보하겠습니다.",
                    ],
                },
                "round3": {
                    "summary": (
                        f"세 패널의 인사이트를 조합하면 {topic} 을/를 단계적으로 확장하면서도 통제를 유지할 수 있습니다."
                    ),
                    "conclusion": (
                        "1) 파일럿-평가-확장 구조를 명확히 정의하고, 2) 실험·리스크·거버넌스를 분리된 태스크포스로 운영하며, "
                        "3) 관찰자에게 모든 의사결정 로그를 공유하면 균형 잡힌 실행이 가능합니다."
                    ),
                    "recommendations": [
                        "파일럿 단계, 확장 단계에 대한 RACI 차트를 작성하세요.",
                        "리스크 대응과 실험 설계를 담당하는 역할을 구분하여 충돌을 줄이세요.",
                    ],
                },
            },
        }

        # Round 1: independent analyses
        for persona, script in panel_scripts.items():
            content_lines = [
                f"### 라운드 1 — {persona} ({script['tagline']})",
                "",
                "**독립 분석**",
                "",
                script["round1"]["summary"],
                "",
                "**핵심 포인트**",
            ]
            content_lines.extend([f"- {point}" for point in script["round1"]["bullets"]])
            content_lines.extend(["", "**우려 요소**"])
            content_lines.extend([f"- {risk}" for risk in script["round1"]["risks"]])
            content_lines.extend(["", "**기회 요소**"])
            content_lines.extend([f"- {opportunity}" for opportunity in script["round1"]["opportunities"]])
            content_lines.extend(["", f"_요약 지침: {instruction}_"])

            self._save_message_and_stream(
                review_id,
                review_room_id,
                "\n".join(content_lines),
                timestamp=round_timestamp,
            )
            round_timestamp += 1

        try:
            self.storage.update_review(review_id, {"current_round": 1})
        except Exception as update_error:
            logger.warning(
                "Failed to update current_round after round 1 in mock review.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        # Round 2: rebuttals based on summaries
        for persona, script in panel_scripts.items():
            content_lines = [
                f"### 라운드 2 — {persona} ({script['tagline']})",
                "",
                "**다른 패널 요약 확인**",
            ]
            content_lines.extend([f"- {ack}" for ack in script["round2"]["ack"]])
            content_lines.extend(["", "**조정하거나 보완할 부분**"])
            content_lines.extend([f"- {dis}" for dis in script["round2"]["disagree"]])
            content_lines.extend(["", "**추가 제안**"])
            content_lines.extend([f"- {addition}" for addition in script["round2"]["additions"]])
            content_lines.extend(["", f"_요약 지침: {instruction}_"])

            self._save_message_and_stream(
                review_id,
                review_room_id,
                "\n".join(content_lines),
                timestamp=round_timestamp,
            )
            round_timestamp += 1

        try:
            self.storage.update_review(review_id, {"current_round": 2})
        except Exception as update_error:
            logger.warning(
                "Failed to update current_round after round 2 in mock review.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        # Round 3: final synthesis per panelist
        for persona, script in panel_scripts.items():
            content_lines = [
                f"### 라운드 3 — {persona} ({script['tagline']})",
                "",
                "**최종 결론**",
                "",
                script["round3"]["summary"],
                "",
                script["round3"]["conclusion"],
                "",
                "**실행 권장 사항**",
            ]
            content_lines.extend([f"- {rec}" for rec in script["round3"]["recommendations"]])
            content_lines.extend(["", f"_요약 지침: {instruction}_"])

            self._save_message_and_stream(
                review_id,
                review_room_id,
                "\n".join(content_lines),
                timestamp=round_timestamp,
            )
            round_timestamp += 1

        try:
            self.storage.update_review(review_id, {"current_round": 3})
        except Exception as update_error:
            logger.warning(
                "Failed to update current_round after round 3 in mock review.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        final_report = {
            "executive_summary": (
                f"세 명의 패널은 {topic} 을/를 빠르게 실험하면서도 통제 장치를 갖추는 전략이 가장 현실적이라고 합의했습니다."
            ),
            "strongest_consensus": [
                "소규모 파일럿을 통해 학습하고, 성공 지표를 조기에 정의한다.",
                "보안·규제 점검 체크리스트를 마련해 리스크를 지속적으로 관리한다.",
            ],
            "remaining_disagreements": [
                "실험 속도에 대한 허용치와 투자 강도는 추가 합의가 필요합니다.",
            ],
            "recommendations": [
                "2주 단위 실험/리뷰 리듬을 세팅하고, 결과를 전사에 공유합니다.",
                f"{topic} 관련 핵심 지표와 리스크 로그를 실시간으로 추적하는 대시보드를 구축합니다.",
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
            redis_pubsub_manager.publish_sync(
                f"review_{review_id}",
                WebSocketMessage(
                    type="status_update",
                    review_id=review_id,
                    payload={"status": "completed"},
                ).model_dump_json(),
            )

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
            parent_room = self.storage.get_room(parent_id)
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

                intro_message = build_intro_message(topic, instruction)
                self._save_message_and_stream(
                    review_id=review_id,
                    review_room_id=room_id,
                    content=intro_message,
                    user_id="observer",
                    role="assistant",
                )

                trace_id = str(uuid.uuid4())
                available_providers = llm_service.get_available_providers()
                panel_configs = llm_strategy_service.get_default_panelists()
                usable_panelists = [p for p in panel_configs if p.provider in available_providers]

                if not usable_panelists:
                    self._run_mock_review(
                        review_id=review_id,
                        review_room_id=room_id,
                        topic=topic,
                        instruction=instruction,
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

                return CreateReviewRoomInteractiveResponse(status="needs_more_context", question=question)
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
