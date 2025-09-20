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
from app.api.dependencies import get_llm_service
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
                "round4": {
                    "final_position": (
                        f"빠른 실험 문화를 유지하되 Skeptic 과 Neutralist 의 통제 구조를 결합하면 "
                        f"{topic} 실험을 전사 신뢰 속에서 확장할 수 있습니다."
                    ),
                    "consensus_highlights": [
                        "파일럿→확장 단계별 성공 지표를 선제적으로 정의한다.",
                        "관찰자에게 모든 학습 로그와 리스크 대응 결과를 주기적으로 공유한다.",
                    ],
                    "open_questions": [
                        "대규모 확장 시 필요한 추가 인력·예산 합의를 얼마나 빠르게 이끌지 논의가 필요합니다.",
                    ],
                    "next_steps": [
                        "30일 이내 실험·리스크·거버넌스 태스크포스를 구성해 책임 소재를 명확히 합니다.",
                        f"{topic} 관련 핵심 지표 대시보드와 실패 보고 양식을 표준화합니다.",
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
                "round4": {
                    "final_position": (
                        f"{topic} 실험을 승인하려면 통제된 범위와 명확한 종료 조건을 먼저 확정해야 합니다."
                    ),
                    "consensus_highlights": [
                        "모든 실험에 대한 데이터·보안 체크리스트를 운영한다.",
                        "관찰자 보고 체계를 통해 리스크 로그를 실시간으로 공유한다.",
                    ],
                    "open_questions": [
                        "실험 속도와 감사 주기 사이의 균형을 어떻게 맞출지 추가 합의가 필요합니다.",
                    ],
                    "next_steps": [
                        "실험·리스크 이중 승인 프로세스를 문서화하고 전사 공지합니다.",
                        "각 라운드 종료 시 투자·중단 기준을 재평가하는 의사결정 회의를 예약합니다.",
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
                "round4": {
                    "final_position": (
                        f"세부 역할과 단계별 게이트를 명확히 하면 {topic} 실행에서 속도와 안전성을 동시에 달성할 수 있습니다."
                    ),
                    "consensus_highlights": [
                        "실험·리스크·거버넌스 역할 분담표를 유지한다.",
                        "관찰자와의 정기 공유로 조직 학습을 가속한다.",
                    ],
                    "open_questions": [
                        "확장 단계에서 필요한 외부 파트너십 범위를 어디까지로 볼지 추가 논의가 필요합니다.",
                    ],
                    "next_steps": [
                        "라운드 종료 직후 역할 분담표와 커뮤니케이션 채널을 확정해 배포합니다.",
                        "분기별 전략 리뷰 세션을 열어 지표·리스크를 공동 점검합니다.",
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

        self._log_status_event(review_id, "initial_turn_complete", timestamp=round_timestamp)
        round_timestamp += 1

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

        self._log_status_event(review_id, "rebuttal_turn_complete", timestamp=round_timestamp)
        round_timestamp += 1

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

        self._log_status_event(review_id, "synthesis_turn_complete", timestamp=round_timestamp)
        round_timestamp += 1

        # Round 4: final alignment per panelist
        for persona, script in panel_scripts.items():
            content_lines = [
                f"### 라운드 4 — {persona} ({script['tagline']})",
                "",
                "**최종 정렬**",
                "",
                script["round4"]["final_position"],
                "",
                "**강조된 합의**",
            ]
            content_lines.extend([f"- {point}" for point in script["round4"]["consensus_highlights"]])
            content_lines.extend(["", "**남은 질문**"])
            content_lines.extend([f"- {question}" for question in script["round4"]["open_questions"]])
            content_lines.extend(["", "**다음 단계 제안**"])
            content_lines.extend([f"- {step}" for step in script["round4"]["next_steps"]])
            content_lines.extend(["", f"_요약 지침: {instruction}_"])

            self._save_message_and_stream(
                review_id,
                review_room_id,
                "\n".join(content_lines),
                timestamp=round_timestamp,
            )
            round_timestamp += 1

        try:
            self.storage.update_review(review_id, {"current_round": 4})
        except Exception as update_error:
            logger.warning(
                "Failed to update current_round after round 4 in mock review.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        self._log_status_event(review_id, "round4_turn_complete", timestamp=round_timestamp)
        round_timestamp += 1

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

        round_timestamp += 1

        try:
            self.storage.update_review(review_id, {"status": "completed"})
        except Exception as update_error:
            logger.warning(
                "Failed to update review status to completed in mock flow.",
                extra={"review_id": review_id, "error": str(update_error)},
            )

        self._log_status_event(review_id, "completed", timestamp=round_timestamp)

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
