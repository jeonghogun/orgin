"""Service helpers for generating contextual content when creating sub rooms."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from app.core.alerts import AlertSeverity, alert_manager
from app.models.schemas import Message
from app.services.storage_service import StorageService, get_storage_service
from app.services.memory_service import MemoryService, get_memory_service
from app.utils.helpers import generate_id, get_current_timestamp

logger = logging.getLogger(__name__)


@dataclass
class SubRoomContextRequest:
    parent_room_id: str
    new_room_name: str
    new_room_id: str
    user_id: str


class SubRoomContextService:
    """Encapsulates the logic for populating new sub rooms with contextual content."""

    def __init__(
        self,
        storage_service: Optional[StorageService] = None,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        self._storage = storage_service or get_storage_service()
        self._memory: Optional[MemoryService] = memory_service or get_memory_service()

    async def initialize_sub_room(self, request: SubRoomContextRequest) -> Optional[Message]:
        """Generate and persist the initial message for a new sub room."""
        parent_messages = await self._load_parent_messages(request.parent_room_id)
        persona_lines = await self._load_user_persona(request.user_id)

        try:
            content = self._build_initial_content(request, parent_messages, persona_lines)
        except Exception as exc:  # pragma: no cover - defensive log
            logger.warning(
                "Sub room contextualisation failed for %s: %s",
                request.new_room_name,
                exc,
                exc_info=True,
            )
            content = None

        if not content:
            content = self._fallback_message(request.new_room_name)
            await self._notify_fallback(request)

        message = Message(
            message_id=generate_id("msg"),
            room_id=request.new_room_id,
            user_id="system",
            role="assistant",
            content=content,
            timestamp=get_current_timestamp(),
        )

        try:
            await asyncio.to_thread(self._storage.save_message, message)
        except Exception as persist_error:  # pragma: no cover - logging
            logger.error(
                "Failed to persist initial message for sub room %s (%s): %s",
                request.new_room_name,
                request.new_room_id,
                persist_error,
                exc_info=True,
            )
            return None
        return message

    async def _load_parent_messages(self, room_id: str) -> List[Message]:
        try:
            messages = await asyncio.to_thread(self._storage.get_messages, room_id)
        except Exception as fetch_error:
            logger.warning(
                "Failed to load conversation history for parent room %s: %s",
                room_id,
                fetch_error,
                exc_info=True,
            )
            return []

        return list(messages)

    def _build_initial_content(
        self,
        request: SubRoomContextRequest,
        parent_messages: List[Message],
        persona_lines: List[str],
    ) -> Optional[str]:
        highlights = self._extract_related_highlights(parent_messages, request.new_room_name)

        if not highlights and not persona_lines:
            return None

        lines: List[str] = [f"'{request.new_room_name}' 세부룸을 시작합니다."]

        if highlights:
            lines.append("최근 대화에서 이어볼 만한 메모:")
            lines.extend(f"- {item}" for item in highlights)

        if persona_lines:
            lines.append("사용자 페르소나 참고:")
            lines.extend(f"- {item}" for item in persona_lines)

        lines.append("주제에 맞춰 자유롭게 대화를 이어가 주세요.")
        return "\n".join(lines)

    def _extract_related_highlights(
        self,
        messages: List[Message],
        topic: str,
    ) -> List[str]:
        if not messages or not topic:
            return []

        normalized_topic = topic.lower()
        keywords = [
            token
            for token in re.split(r"[\s,.;!?()\[\]{}\-_/]+", normalized_topic)
            if len(token) >= 2
        ]

        related: List[str] = []
        blocklisted_phrases = ["파일", "업로드", "첨부", "이미지", "스크린샷", "Interaction_Error", "로그"]
        for message in messages:
            role = (getattr(message, "role", "") or "").lower()
            if role not in {"user", "assistant"}:
                continue
            content = (getattr(message, "content", "") or "").strip()
            if not content:
                continue

            if any(keyword in content for keyword in blocklisted_phrases):
                continue

            if role != "user":
                lowered_content = content.lower()
                if not (normalized_topic and (normalized_topic in lowered_content or any(keyword in lowered_content for keyword in keywords))):
                    continue
            else:
                lowered_content = content.lower()
                if normalized_topic and not (
                    normalized_topic in lowered_content or any(keyword in lowered_content for keyword in keywords)
                ):
                    continue

            lowered = content.lower()
            if normalized_topic in lowered or any(keyword in lowered for keyword in keywords):
                trimmed = content.replace("\n", " ").strip()
                if len(trimmed) > 160:
                    trimmed = trimmed[:157].rstrip() + "..."
                related.append(trimmed)

        # Provide the most recent highlights, keeping the room lightweight.
        return related[-3:]

    def _fallback_message(self, topic: str) -> str:
        return (
            f"'{topic}' 세부룸이 열렸습니다. 반가워요! 관련 아이디어를 편하게 나눠 주세요."
        )

    async def _load_user_persona(self, user_id: str) -> List[str]:
        if not user_id or not self._memory:
            return []

        try:
            profile = await self._memory.get_user_profile(user_id)
        except Exception as profile_error:  # pragma: no cover - defensive log
            logger.debug("Failed to load user profile for sub room context (user=%s): %s", user_id, profile_error)
            return []

        if not profile:
            return []

        persona_lines: List[str] = []

        name = getattr(profile, "name", None)
        if isinstance(name, str) and name.strip():
            persona_lines.append(f"이름: {name.strip()}")

        conversation_style = getattr(profile, "conversation_style", None)
        if isinstance(conversation_style, str) and conversation_style.strip() and conversation_style.strip() != "default":
            persona_lines.append(f"대화 스타일: {conversation_style.strip()}")

        interests = getattr(profile, "interests", None)
        if isinstance(interests, list):
            trimmed_interests = [interest for interest in interests if isinstance(interest, str) and interest.strip()]
            if trimmed_interests:
                persona_lines.append("관심사: " + ", ".join(trimmed_interests[:3]))

        return persona_lines[:3]

    async def _notify_fallback(self, request: SubRoomContextRequest) -> None:
        try:
            await alert_manager.send_manual_alert(
                title="Sub room context fallback triggered",
                message=(
                    "LLM-based contextualization failed. Serving default message instead."
                ),
                severity=AlertSeverity.WARNING,
                source="sub_room_context",
                metadata={
                    "room_id": request.new_room_id,
                    "parent_room_id": request.parent_room_id,
                    "topic": request.new_room_name,
                },
            )
        except Exception as alert_error:  # pragma: no cover - logging only
            logger.debug("Alert dispatch failed: %s", alert_error)


def get_sub_room_context_service() -> SubRoomContextService:
    return SubRoomContextService()
