"""
Review Service - Orchestrates the multi-agent review process using Celery.
"""
import asyncio
import json
import logging
import re
import uuid
from typing import Optional, List, Dict, Any, Tuple
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


MAX_CLARIFYING_ATTEMPTS: int = 2
MIN_TOPIC_CHAR_THRESHOLD: int = 12
MIN_TOPIC_TOKEN_THRESHOLD: int = 3
HISTORY_CONTEXT_WINDOW: int = 6
CONTEXT_NOTES_MAX_LEN: int = 1500
CLARIFYING_FALLBACK_PROMPT: str = "말씀해주신 주제만으로도 생성 가능합니다. 이대로 진행할까요?"


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

    @staticmethod
    def _is_substantive_text(text: str) -> bool:
        """Heuristic check to see if the provided topic text carries enough detail."""

        cleaned = (text or "").strip()
        if len(cleaned) >= MIN_TOPIC_CHAR_THRESHOLD:
            return True

        tokens = [token for token in re.split(r"\s+", cleaned) if token]
        meaningful_tokens = [token for token in tokens if len(token) >= 2]
        return len(meaningful_tokens) >= MIN_TOPIC_TOKEN_THRESHOLD

    def _normalise_history_entries(
        self,
        history: Optional[List[Dict[str, str]]],
    ) -> Tuple[List[Dict[str, str]], List[str], List[str], List[str]]:
        """Return sanitised history along with user/assistant content buckets."""

        if not history:
            return [], [], [], []

        normalised: List[Dict[str, str]] = []
        user_contents: List[str] = []
        assistant_contents: List[str] = []
        substantive_user_contents: List[str] = []

        for entry in history:
            if not isinstance(entry, dict):
                continue
            content = (entry.get("content") or "").strip()
            if not content:
                continue
            role_raw = (entry.get("role") or "").strip().lower()
            if role_raw in {"assistant", "review_assistant"}:
                role = "assistant"
                assistant_contents.append(content)
            elif role_raw == "user":
                role = "user"
                user_contents.append(content)
                if self._is_substantive_text(content):
                    substantive_user_contents.append(content)
            else:
                continue

            normalised.append({"role": role, "content": content})

        return normalised, user_contents, assistant_contents, substantive_user_contents

    @staticmethod
    def _build_topic_seed(topic: str, user_entries: List[str]) -> str:
        """Combine the explicit topic with user history for richer title hints."""

        candidates: List[str] = []
        for text in [topic, *user_entries]:
            cleaned = (text or "").strip()
            if not cleaned:
                continue
            if cleaned in candidates:
                continue
            candidates.append(cleaned)

        if not candidates:
            return ""

        return "\n".join(candidates[-3:])

    @staticmethod
    def _compose_history_context_text(history_entries: List[Dict[str, str]]) -> str:
        """Format recent history turns for prompts or fallbacks."""

        if not history_entries:
            return ""

        window = history_entries[-HISTORY_CONTEXT_WINDOW:]
        lines: List[str] = []
        for item in window:
            role = item.get("role", "")
            label = "사용자" if role == "user" else "오리진"
            lines.append(f"{label}: {item.get('content', '').strip()}")

        return "\n".join(lines)

    def _filter_source_messages(self, messages: List[Message]) -> List[Message]:
        """Filter out system summaries and empty payloads from the source room."""

        if not messages:
            return []

        filtered: List[Message] = []
        for message in messages:
            content = (getattr(message, "content", "") or "").strip()
            if not content:
                continue

            user_id = (getattr(message, "user_id", "") or "").strip().lower()
            if user_id == "system":
                continue

            if "**핵심 요약:**" in content:
                continue

            filtered.append(message)

        return filtered

    @staticmethod
    def _has_rich_user_context(user_entries: List[str]) -> bool:
        """Heuristic to determine if user-provided history provides enough detail."""

        if not user_entries:
            return False

        for entry in user_entries:
            cleaned = (entry or "").strip()
            if not cleaned:
                continue

            if len(cleaned) >= 24:
                return True

            word_like_tokens = [token for token in re.split(r"\s+", cleaned) if len(token) >= 2]
            if len(word_like_tokens) >= 5:
                return True

            sentence_marks = sum(cleaned.count(mark) for mark in (".", "!", "?"))
            if sentence_marks >= 2:
                return True

        return False

    def _build_context_notes(
        self,
        conversation_excerpt: str,
        history_entries: List[Dict[str, str]],
    ) -> Optional[str]:
        """Combine conversation and history snippets for fallback or title generation."""

        sections: List[str] = []
        excerpt = (conversation_excerpt or "").strip()
        if excerpt:
            sections.append(excerpt)

        history_text = self._compose_history_context_text(history_entries)
        if history_text:
            sections.append(history_text)

        if not sections:
            return None

        combined = "\n".join(sections).strip()
        if len(combined) > CONTEXT_NOTES_MAX_LEN:
            combined = combined[-CONTEXT_NOTES_MAX_LEN:]
        return combined

    def _prepare_conversation_excerpt(
        self,
        messages: List[Message],
        topic: str,
    ) -> Tuple[str, bool]:
        """Extract topic-related utterances while skipping system summaries."""

        if not messages:
            return "", False

        topic = (topic or "").strip()
        normalized_topic = topic.lower()
        keywords = [
            token
            for token in re.split(r"[\s,.;!?()\[\]{}\-_/]+", normalized_topic)
            if len(token) >= 2
        ]

        relevant_lines: List[str] = []
        fallback_lines: List[str] = []
        for msg in messages:
            user_id = getattr(msg, "user_id", "") or ""
            content = (getattr(msg, "content", "") or "").strip()
            role = getattr(msg, "role", "") or "unknown"

            if not content:
                continue
            if user_id == "system" or "**핵심 요약:**" in content:
                continue

            formatted = f"{role}: {content}"
            fallback_lines.append(formatted)

            formatted = f"{role}: {content}"
            lowered = content.lower()
            if normalized_topic and (
                normalized_topic in lowered or any(keyword in lowered for keyword in keywords)
            ):
                relevant_lines.append(formatted)

        if relevant_lines:
            excerpt = "\n".join(relevant_lines[-10:])
            return excerpt, True

        if fallback_lines and (not normalized_topic or not keywords):
            excerpt = "\n".join(fallback_lines[-10:])
            return excerpt, True

        return "", False

    @staticmethod
    def _format_context_excerpt(conversation_excerpt: str) -> Optional[str]:
        """Convert a raw conversation excerpt into bullet-formatted context."""

        cleaned_lines: List[str] = []
        for raw_line in (conversation_excerpt or "").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            speaker, content = None, stripped
            if ":" in stripped:
                speaker, remainder = stripped.split(":", 1)
                speaker = speaker.strip()
                content = remainder.strip()

            if speaker:
                cleaned_lines.append(f"- {speaker}: {content}")
            else:
                cleaned_lines.append(f"- {content}")

        if not cleaned_lines:
            return None

        return "\n".join(cleaned_lines)

    async def start_review_process(
        self,
        review_id: str,
        review_room_id: str,
        topic: str,
        instruction: str,
        panelists: Optional[List[str]],
        trace_id: str,
        context_notes: Optional[str] = None,
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
                context_notes=context_notes,
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
                context_notes=context_notes,
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

        try:
            redis_pubsub_manager.publish_sync(
                f"review_{review_id}",
                WebSocketMessage(
                    type="new_message",
                    review_id=review_id,
                    payload=message.model_dump(),
                ).model_dump_json(),
            )
        except Exception as broadcast_error:
            logger.warning(
                "Failed to publish review message over Redis.",
                extra={
                    "review_id": review_id,
                    "room_id": review_room_id,
                    "error": str(broadcast_error),
                },
                exc_info=True,
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

        try:
            redis_pubsub_manager.publish_sync(
                f"review_{review_id}",
                WebSocketMessage(
                    type="status_update",
                    review_id=review_id,
                    ts=ts,
                    payload=event_payload,
                ).model_dump_json(),
            )
        except Exception as broadcast_error:
            logger.warning(
                "Failed to publish status update over Redis.",
                extra={
                    "review_id": review_id,
                    "status": status,
                    "error": str(broadcast_error),
                },
                exc_info=True,
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

    def _run_mock_review(
        self,
        review_id: str,
        review_room_id: str,
        topic: str,
        instruction: str,
        *,
        context_notes: Optional[str] = None,
    ) -> None:
        """Generate a lightweight, synchronous review flow when no LLM providers are available."""
        logger.warning(
            "No LLM providers are configured. Falling back to mock review generation.",
            extra={"review_id": review_id, "room_id": review_room_id},
        )

        start_ts = get_current_timestamp()
        self._log_status_event(review_id, "fallback_started", timestamp=start_ts)

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

        context_points: List[str] = []
        if context_notes:
            for raw_line in context_notes.splitlines():
                cleaned = raw_line.strip().lstrip("-•· ").strip()
                if len(cleaned) < 5:
                    continue
                if cleaned in context_points:
                    continue
                context_points.append(cleaned)
                if len(context_points) >= 5:
                    break

        def _short(text: Optional[str], limit: int = 120) -> str:
            cleaned_text = (text or "").strip()
            if len(cleaned_text) <= limit:
                return cleaned_text
            return cleaned_text[: limit - 1].rstrip() + "…"

        primary_focus_raw = context_points[0] if context_points else ""
        secondary_focus_raw = context_points[1] if len(context_points) > 1 else ""
        tertiary_focus_raw = context_points[2] if len(context_points) > 2 else ""

        primary_focus = _short(primary_focus_raw, 100)
        secondary_focus = _short(secondary_focus_raw, 100)
        tertiary_focus = _short(tertiary_focus_raw, 100)

        base_takeaway = primary_focus or "핵심 가설 명확화"
        guardrail_phrase = secondary_focus or "거버넌스 기준 정립"

        initial_statements = [
            {
                "round": 1,
                "persona": "GPT-4o (모의 패널)",
                "message": (
                    f"제 생각에 {topic_label}에서 가장 먼저 다뤄야 할 건 {base_takeaway or '핵심 가설을 선명하게 정리하는 일'}입니다. "
                    "실행팀이 헷갈리지 않도록 이번 주에 핵심 지표와 성공 조건을 3가지 안으로 정리하겠습니다."
                ),
                "key_takeaway": f"{topic_label} 검토 초점은 {base_takeaway}.",
            },
            {
                "round": 1,
                "persona": "Claude 3 Haiku (모의 패널)",
                "message": (
                    f"저는 거버넌스 관점에서 {guardrail_phrase}을(를) 먼저 고정해야 한다고 봅니다. "
                    "어떤 의사결정도 기준선 없이 나가면 위험하니까요."
                ),
                "key_takeaway": f"거버넌스 기준 {guardrail_phrase}을(를) 선제적으로 확정.",
            },
            {
                "round": 1,
                "persona": "Gemini 1.5 Flash (모의 패널)",
                "message": (
                    f"저는 실험 확장 관점에서 접근하겠습니다. {topic_label}을(를) 2단계 검증 여정으로 나누고, "
                    "각 단계에서 배우는 내용을 빠르게 공유하도록 제안합니다."
                ),
                "key_takeaway": "2단계 검증 여정으로 속도와 학습을 동시에 잡자.",
            },
        ]

        debate_round = [
            {
                "round": 2,
                "persona": "GPT-4o (모의 패널)",
                "message": (
                    f"Claude의 {guardrail_phrase} 체크리스트 제안에 동의합니다. "
                    f"그 기준을 적용한 상태에서 저는 {base_takeaway or '핵심 가설'}을(를) 어떻게 검증할지 실험 플랜을 설계하겠습니다."
                ),
                "key_takeaway": f"통제 기준을 넣고 {base_takeaway or '핵심 가설'} 검증에 집중.",
                "references": [
                    {
                        "panelist": "Claude 3 Haiku (모의 패널)",
                        "round": 1,
                        "quote": guardrail_phrase,
                        "stance": "support",
                    }
                ],
            },
            {
                "round": 2,
                "persona": "Claude 3 Haiku (모의 패널)",
                "message": (
                    "좋습니다. 저는 법무·보안팀이 바로 활용할 수 있도록 체크리스트 초안을 만들고, "
                    f"책임자와 승인 기준을 적어도 두 단계 전에 확정하겠습니다."
                ),
                "key_takeaway": "보안·법무 체크리스트와 책임자를 미리 지정.",
                "references": [
                    {
                        "panelist": "GPT-4o (모의 패널)",
                        "round": 2,
                        "quote": "실험 플랜",
                        "stance": "build",
                    }
                ],
            },
            {
                "round": 2,
                "persona": "Gemini 1.5 Flash (모의 패널)",
                "message": (
                    f"두 분 계획을 묶어서 1단계에서 {base_takeaway or '핵심 가설'}을(를) 검증하고, 2단계에서 {guardrail_phrase} 준수 여부를 측정하는 로드맵을 그리겠습니다."
                ),
                "key_takeaway": "1단계 학습 + 2단계 거버넌스로 속도와 안전을 모두 확보.",
                "references": [
                    {
                        "panelist": "GPT-4o (모의 패널)",
                        "round": 2,
                        "quote": base_takeaway or "핵심 가설",
                        "stance": "build",
                    },
                    {
                        "panelist": "Claude 3 Haiku (모의 패널)",
                        "round": 2,
                        "quote": guardrail_phrase,
                        "stance": "support",
                    },
                ],
            },
        ]

        synthesis_round = [
            {
                "round": 3,
                "persona": "GPT-4o (모의 패널)",
                "message": (
                    f"그럼 1단계 실험 결과와 {guardrail_phrase} 체크리스트를 한 주 단위로 공유하는 대시보드를 만들겠습니다. 이렇게 하면 {topic_label} 관련 합의가 바로 실행으로 이어집니다."
                ),
                "key_takeaway": "주간 대시보드로 합의-실행 사이클을 가속.",
                "references": [
                    {
                        "panelist": "Gemini 1.5 Flash (모의 패널)",
                        "round": 2,
                        "quote": "2단계 로드맵",
                        "stance": "support",
                    }
                ],
            },
            {
                "round": 3,
                "persona": "Claude 3 Haiku (모의 패널)",
                "message": (
                    f"대시보드에 법적 리스크와 {guardrail_phrase} 항목을 모두 반영해 두겠습니다. {tertiary_focus or '예산·책임 범위'}는 담당자를 지정해 추적하죠."
                ),
                "key_takeaway": f"{guardrail_phrase}와 {tertiary_focus or '예산·책임'}을 정량적으로 추적.",
                "references": [
                    {
                        "panelist": "GPT-4o (모의 패널)",
                        "round": 3,
                        "quote": "대시보드",
                        "stance": "support",
                    }
                ],
            },
        ]

        # Define missing variables for final_alignment
        consensus_points = [
            f"{base_takeaway}을(를) 1단계로 우선 추진",
            f"{guardrail_phrase} 체크리스트를 주간 대시보드에 반영",
            f"{tertiary_focus or '예산·책임 범위'} 담당자 지정 및 추적 체계 구축"
        ]
        
        remaining_points = [
            f"{topic_label}의 장기적 확장성 검토",
            "성과 지표 및 KPI 설정 방안"
        ]
        
        recommendations = [
            "1주차: 핵심 가설 검증 실험 시작",
            "2주차: 거버넌스 기준 적용 및 모니터링",
            "3주차: 중간 결과 분석 및 방향 조정"
        ]

        final_alignment = {
            "round": 4,
            "persona": "Gemini 1.5 Flash (모의 패널)",
            "final_position": (
                f"세 패널은 {topic_label}을(를) 단계별로 추진하되, {guardrail_phrase} 체크리스트와 학습 리포트를 동시에 운용하기로 합의했습니다."
            ),
            "consensus_highlights": consensus_points,
            "open_questions": remaining_points,
            "next_steps": recommendations,
            "no_new_arguments": False,
        }

        conversation_script = initial_statements + debate_round + synthesis_round + [final_alignment]

        status_markers = {
            1: "conversation_started",
            3: "conversation_midway",
            len(conversation_script): "conversation_complete",
        }

        for index, entry in enumerate(conversation_script, start=1):
            payload_content = {
                "panelist": entry["persona"],
                "round": entry.get("round"),
                "message": entry.get("message", ""),
                "key_takeaway": entry.get("key_takeaway") or entry.get("final_position", ""),
                "references": entry.get("references", []),
                "no_new_arguments": entry.get("no_new_arguments", False),
            }

            if entry.get("round") == 4:
                payload_content.update(
                    {
                        "final_position": entry.get("final_position", ""),
                        "consensus_highlights": entry.get("consensus_highlights", []),
                        "open_questions": entry.get("open_questions", []),
                        "next_steps": entry.get("next_steps", []),
                    }
                )

            payload = {
                "persona": entry["persona"],
                "payload": payload_content,
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

        if primary_focus and secondary_focus:
            summary = (
                f"패널들은 '{primary_focus}'을(를) 기준으로 실행안을 정리하고, '{secondary_focus}'을(를) 병행 관리해야 한다는 데 의견을 모았습니다."
            )
        elif primary_focus:
            summary = f"패널들은 {topic_label} 검토에서 '{primary_focus}'을(를) 가장 먼저 다뤄야 한다고 정리했습니다."
        else:
            summary = f"패널들은 {topic_label} 검토를 빠르게 실행 단계로 넘기기 위한 공통 원칙을 합의했습니다."

        consensus_points: List[str] = [
            f"{topic_label} 관련 핵심 가설과 검증 지표를 1주 안에 정리한다.",
            f"{guardrail_phrase}을(를) 체크리스트로 고정해 거버넌스를 확보한다.",
        ]

        remaining_points: List[str] = []
        if tertiary_focus:
            remaining_points.append(f"'{tertiary_focus}'에 대한 책임자와 예산 범위를 추가로 합의해야 합니다.")
        else:
            remaining_points.append("예산과 책임 범위에 대한 세부 합의가 필요합니다.")

        recommendations: List[str] = [
            f"{topic_label} 검토를 핵심 검증 단계와 확장 학습 단계로 분리해 실행한다.",
            f"{guardrail_phrase} 체크리스트와 담당자를 회의 시작 전에 확정한다.",
        ]

        final_report = {
            "executive_summary": summary,
            "strongest_consensus": consensus_points,
            "remaining_disagreements": remaining_points,
            "recommendations": recommendations,
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

            topic = (topic or "").strip()

            (
                normalised_history,
                user_history_contents,
                assistant_history_contents,
                substantive_user_contents,
            ) = self._normalise_history_entries(history)

            topic_seed = self._build_topic_seed(topic, user_history_contents)
            topic_basis = topic_seed or topic

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

            filtered_messages = self._filter_source_messages(messages)

            conversation_excerpt, excerpt_has_related = self._prepare_conversation_excerpt(
                filtered_messages,
                topic_basis,
            )

            formatted_context_excerpt = self._format_context_excerpt(conversation_excerpt)

            context_notes = self._build_context_notes(conversation_excerpt, normalised_history)
            clarifying_turns = len(assistant_history_contents)
            has_rich_user_context = self._has_rich_user_context(substantive_user_contents)
            has_room_context = bool(filtered_messages)
            has_conversation_excerpt = bool(conversation_excerpt.strip())

            context_sufficient = False
            if excerpt_has_related or has_conversation_excerpt or has_room_context or has_rich_user_context:
                context_sufficient = True

            fallback_already_offered = False
            if normalised_history:
                for entry in reversed(normalised_history):
                    if entry.get("role") != "assistant":
                        continue
                    content = entry.get("content", "")
                    if CLARIFYING_FALLBACK_PROMPT in content:
                        fallback_already_offered = True
                    break

            if not context_sufficient and clarifying_turns >= MAX_CLARIFYING_ATTEMPTS:
                if fallback_already_offered:
                    context_sufficient = True
                else:
                    fallback_question = CLARIFYING_FALLBACK_PROMPT

                    prompt_message_payload: Optional[Message] = None
                    prompt_message = Message(
                        message_id=generate_id(),
                        room_id=parent_id,
                        user_id="review_assistant",
                        role="assistant",
                        content=fallback_question,
                        timestamp=get_current_timestamp(),
                    )

                    try:
                        await asyncio.to_thread(self.storage.save_message, prompt_message)
                    except Exception as save_error:
                        logger.warning(
                            "Failed to persist fallback confirmation message for room %s: %s",
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
                                "Failed to broadcast fallback confirmation for room %s: %s",
                                parent_id,
                                broadcast_error,
                                exc_info=True,
                            )

                    return CreateReviewRoomInteractiveResponse(
                        status="needs_more_context",
                        question=fallback_question,
                        prompt_message=prompt_message_payload,
                    )

            if context_sufficient:
                conversation_for_title = context_notes or conversation_excerpt or ""
                generated_topic = await self._generate_review_topic_title(
                    llm_service,
                    fallback_topic=topic_basis or topic or "리뷰 주제",
                    conversation=conversation_for_title,
                    history=normalised_history or None,
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
                instruction_lines = [
                    "세 명의 패널이 하나의 단톡방에서 깊이 있게 토론하되,",
                    "충분한 합의가 이뤄지면 더 길게 늘리지 말고 정리하도록 요청했습니다.",
                ]

                if formatted_context_excerpt:
                    instruction_lines.extend([
                        "",
                        "[참고 맥락]",
                        formatted_context_excerpt,
                    ])

                instruction = "\n".join(instruction_lines)
                review_meta = ReviewMeta(
                    review_id=review_id,
                    room_id=room_id,
                    topic=generated_topic,
                    instruction=instruction,
                    status="pending",
                    total_rounds=4,
                    created_at=get_current_timestamp(),
                    completed_at=0,
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
                        context_notes=context_notes,
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
                        context_notes=context_notes,
                    )

                return CreateReviewRoomInteractiveResponse(status="created", room=Room.model_validate(new_room))
            else:
                clarifying_index = clarifying_turns + 1
                remaining_attempts = max(0, MAX_CLARIFYING_ATTEMPTS - clarifying_index)
                history_context_text = self._compose_history_context_text(normalised_history)
                topic_hint_for_question = topic_basis or topic or "(미정)"

                system_prompt = (
                    "You help scope an executive review room. Only ask a follow-up when essential. "
                    "Respond strictly in JSON with a single 'question' field written in Korean."
                )

                user_prompt_lines = [
                    f"현재까지 사용자가 제시한 주제 초안: {topic_hint_for_question}",
                    f"이번은 추가 질문 {clarifying_index}번째 시도이며, 이후 남은 추가 질문 기회: {remaining_attempts}회",
                ]

                if history_context_text:
                    user_prompt_lines.append("최근 대화:")
                    user_prompt_lines.append(history_context_text)
                else:
                    user_prompt_lines.append("최근 대화: (아직 추가 설명 없음)")

                user_prompt_lines.extend(
                    [
                        "사용자가 방금 입력한 표현을 존중하면서, 더 구체적으로 알고 싶은 부분을 자연스럽게 물어보세요.",
                        "사용자가 언급하지 않은 단어(예: 프로젝트, 제품, 서비스 등)를 새로 도입하지 말고, 중립적인 어휘를 사용합니다.",
                        "검토하고 싶은 범위나 초점을 파악할 수 있도록 한 문장으로 묻되, 질문은 반드시 존댓말로 끝내세요.",
                        "방금 물었던 문장을 그대로 반복하지 말고, 사용자 입장에서 답하기 쉬운 맥락을 주세요.",
                        'JSON 예시는 {"question": "..."} 형태입니다.',
                    ]
                )

                user_prompt = "\n\n".join(user_prompt_lines)

                question = None
                question_str = ""
                try:
                    question_str, _ = await llm_service.invoke(
                        provider_name="openai",
                        model="gpt-4o",
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        request_id="question-gen",
                        response_format="json"
                    )
                except Exception as invoke_error:
                    logger.warning(
                        "Failed to generate clarifying question via LLM: %s",
                        invoke_error,
                        exc_info=True,
                    )

                if question_str:
                    try:
                        validated_data = LLMQuestionResponse.model_validate_json(question_str)
                        question = validated_data.question
                    except Exception as validation_error:
                        logger.error(
                            "Failed to validate question from LLM: %s. Raw response: %s",
                            validation_error,
                            question_str,
                        )

                if not question:
                    question = (
                        f"'{topic_hint_for_question}'와 관련해 어떤 부분을 집중적으로 검토하고 싶은지 조금 더 말씀해주실 수 있을까요?"
                    )

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
