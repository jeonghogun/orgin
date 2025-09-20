"""Service helpers for generating contextual content when creating sub rooms."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.config.settings import settings
from app.core.alerts import AlertSeverity, alert_manager
from app.models.schemas import Message
from app.services.llm_service import LLMService, get_llm_service
from app.services.memory_service import MemoryService, get_memory_service
from app.services.storage_service import StorageService, get_storage_service
from app.utils.helpers import generate_id, get_current_timestamp, maybe_await

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
        llm_service: Optional[LLMService] = None,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        self._storage = storage_service or get_storage_service()
        self._llm = llm_service or get_llm_service()
        self._memory = memory_service or get_memory_service()

    async def initialize_sub_room(self, request: SubRoomContextRequest) -> Optional[Message]:
        """Generate and persist the initial message for a new sub room."""
        conversation = await self._load_parent_conversation(request.parent_room_id)
        try:
            content = await self._build_initial_content(request, conversation)
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

    async def _load_parent_conversation(self, room_id: str) -> str:
        try:
            messages = await asyncio.to_thread(self._storage.get_messages, room_id)
        except Exception as fetch_error:
            logger.warning(
                "Failed to load conversation history for parent room %s: %s",
                room_id,
                fetch_error,
                exc_info=True,
            )
            return ""

        fragments = []
        for message in messages:
            role = getattr(message, "role", "")
            content = getattr(message, "content", "")
            if role and content:
                fragments.append(f"{role}: {content}")
        return "\n".join(fragments)

    async def _build_initial_content(
        self,
        request: SubRoomContextRequest,
        conversation: str,
    ) -> Optional[str]:
        if conversation and request.new_room_name.lower() in conversation.lower():
            return await self._summarize_existing_topic(request, conversation)
        return await self._compose_welcome_message(request)

    async def _summarize_existing_topic(
        self,
        request: SubRoomContextRequest,
        conversation: str,
    ) -> Optional[str]:
        system_prompt = (
            "You are a helpful assistant. Summarize the following conversation, focusing on the key points, "
            "facts, and decisions related to the topic. Provide a concise summary."
        )
        user_prompt = f"Topic: '{request.new_room_name}'\n\nConversation:\n{conversation}"

        summary, _ = await self._llm.invoke(
            provider_name="openai",
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id="sub-room-summary",
        )
        return (
            f"이 세부룸은 메인룸의 '{request.new_room_name}' 논의를 기반으로 생성되었습니다.\n\n"
            f"**핵심 요약:**\n{summary}"
        )

    async def _compose_welcome_message(self, request: SubRoomContextRequest) -> Optional[str]:
        profile = await self._safe_profile(request.user_id)
        context = await self._safe_room_context(request.parent_room_id, request.user_id)
        system_prompt = (
            "You are a helpful AI assistant starting a new conversation. Based on the user's profile and the "
            "general context of the main room, generate a welcoming message to kick off the discussion about a new topic."
        )
        user_prompt = (
            f"New Topic: '{request.new_room_name}'\n"
            f"User Profile: {profile.model_dump_json() if profile else 'Not available'}\n"
            f"Main Room Context: {context.model_dump_json() if context else 'Not available'}"
        )
        welcome_message, _ = await self._llm.invoke(
            provider_name="openai",
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id="sub-room-welcome",
        )
        return welcome_message

    async def _safe_profile(self, user_id: str):
        try:
            return await maybe_await(self._memory.get_user_profile(user_id))
        except Exception as profile_error:  # pragma: no cover - logging only
            logger.warning(
                "Failed to load user profile for %s: %s",
                user_id,
                profile_error,
                exc_info=True,
            )
            return None

    async def _safe_room_context(self, room_id: str, user_id: str):
        try:
            return await maybe_await(self._memory.get_context(room_id, user_id))
        except Exception as context_error:  # pragma: no cover - logging only
            logger.warning(
                "Failed to load context for room %s and user %s: %s",
                room_id,
                user_id,
                context_error,
                exc_info=True,
            )
            return None

    def _fallback_message(self, topic: str) -> str:
        return f"'{topic}' 주제의 세부룸이 생성되었습니다. 자유롭게 대화를 이어가 주세요!"

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
