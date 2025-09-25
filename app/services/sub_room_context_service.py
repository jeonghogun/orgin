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
    ) -> None:
        self._storage = storage_service or get_storage_service()

    async def initialize_sub_room(self, request: SubRoomContextRequest) -> Optional[Message]:
        """Generate and persist the initial message for a new sub room."""
        parent_messages = await self._load_parent_messages(request.parent_room_id)
        try:
            content = self._build_initial_content(request, parent_messages)
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
    ) -> Optional[str]:
        highlights = self._extract_related_highlights(parent_messages, request.new_room_name)
        if not highlights:
            return None

        highlight_lines = "\n".join(f"- {item}" for item in highlights)
        return (
            f"'{request.new_room_name}' 세부룸이 열렸습니다.\n"
            "메인룸에서 이어질 만한 메모를 정리했어요:\n"
            f"{highlight_lines}\n"
            "이제 자유롭게 이야기를 이어가 주세요."
        )

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
        for message in messages:
            role = (getattr(message, "role", "") or "").lower()
            if role not in {"user", "assistant"}:
                continue
            content = (getattr(message, "content", "") or "").strip()
            if not content:
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
            f"'{topic}' 세부룸이 열렸습니다. 메인룸과는 독립적으로 가볍게 이야기를 시작해 보세요."
        )

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
