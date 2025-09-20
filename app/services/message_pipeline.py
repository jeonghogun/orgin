"""Shared helpers for orchestrating message workflows.

This module centralizes reusable pieces of the message routing logic so that
FastAPI route handlers stay focused on transport concerns while the actual
processing happens in well scoped helpers.  The functions defined here are
imported by both the REST and streaming endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sse_starlette.sse import EventSourceResponse

from app.models.enums import RoomType
from app.models.schemas import Message, ReviewMeta
from app.services.background_task_service import BackgroundTaskService
from app.services.cache_service import CacheService
from app.services.external_api_service import ExternalSearchService
from app.services.fact_extractor_service import FactExtractorService
from app.services.intent_classifier_service import (
    FactQueryType,
    IntentClassifierService,
)
from app.services.intent_service import IntentService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.realtime_service import RealtimeService
from app.services.review_service import ReviewService
from app.services.storage_service import StorageService
from app.services.user_fact_service import UserFactService
from app.services.fact_types import FactType
from app.utils.helpers import (
    create_success_response,
    generate_id,
    get_current_timestamp,
    maybe_await,
)

logger = logging.getLogger(__name__)

NAME_EXTRACTION_PATTERNS = [
    re.compile(r"(?:내|제|저의)\s*이름(?:은|은요|은지)?\s*([\w가-힣]+)", re.IGNORECASE),
    re.compile(r"(?:나를|저를)\s*([\w가-힣]+)\s*라고\s*불러", re.IGNORECASE),
    re.compile(r"(?:이름은)\s*([\w가-힣]+)", re.IGNORECASE),
]
NAME_EXTRACTION_SUFFIXES = (
    "입니다",
    "이에요",
    "예요",
    "이야",
    "야",
    "라고",
    "라고요",
    "라고해",
)


async def handle_fact_extraction(
    user_fact_service: UserFactService,
    fact_extractor_service: FactExtractorService,
    message: Message,
) -> None:
    """Extract and persist facts from a user message."""

    try:
        if message.role and message.role != "user":
            return

        user_profile = await maybe_await(
            user_fact_service.get_user_profile(message.user_id)
        )
        if user_profile and not getattr(
            user_profile, "auto_fact_extraction_enabled", True
        ):
            logger.info("Fact extraction disabled for user %s", message.user_id)
            return

        raw_facts = await maybe_await(
            fact_extractor_service.extract_facts_from_message(
                message.content, str(message.message_id)
            )
        )
        if not raw_facts:
            return

        logger.info(
            "Extracted %s potential facts from message %s",
            len(raw_facts),
            message.message_id,
        )
        for fact in raw_facts:
            try:
                fact_type_enum = FactType(fact["type"])
            except (KeyError, ValueError):
                logger.warning(
                    "Skipping fact with unknown type: %s",
                    fact.get("type"),
                )
                continue

            normalized_value = fact_extractor_service.normalize_value(
                fact_type_enum, fact.get("value")
            )
            sensitivity = fact_extractor_service.get_sensitivity(fact_type_enum)
            await maybe_await(
                user_fact_service.save_fact(
                    user_id=message.user_id,
                    fact=fact,
                    normalized_value=normalized_value,
                    source_message_id=str(message.message_id),
                    sensitivity=sensitivity.value,
                    room_id=message.room_id,
                )
            )
            logger.info(
                "Saved fact for user %s type=%s",
                message.user_id,
                fact_type_enum.value,
            )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Error during background fact extraction for %s: %s",
            message.message_id,
            exc,
            exc_info=True,
        )


async def ensure_fact_extraction(
    message: Message,
    user_fact_service: UserFactService,
    fact_extractor_service: FactExtractorService,
    *,
    background_tasks: Optional[BackgroundTaskService] = None,
    execute_inline: bool = True,
) -> None:
    """Run fact extraction immediately and/or in the background."""

    if execute_inline:
        try:
            await handle_fact_extraction(
                user_fact_service, fact_extractor_service, message
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Inline fact extraction failed for %s: %s",
                message.message_id,
                exc,
                exc_info=True,
            )

    if background_tasks is None:
        return

    task_id = f"fact_extraction_{message.message_id}"
    try:
        background_tasks.create_background_task(
            task_id,
            handle_fact_extraction,
            user_fact_service,
            fact_extractor_service,
            message,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Failed to schedule fact extraction task %s: %s",
            task_id,
            exc,
            exc_info=True,
        )


async def detect_fact_query(
    content: str, intent_classifier: IntentClassifierService
) -> Optional[FactType]:
    """Detect whether the user is asking for a stored fact."""

    try:
        fact_type = await maybe_await(
            intent_classifier.get_fact_query_type(content)
        )
        if fact_type and fact_type != FactQueryType.NONE:
            mapping = {
                FactQueryType.USER_NAME: FactType.USER_NAME,
                FactQueryType.JOB: FactType.JOB,
                FactQueryType.HOBBY: FactType.HOBBY,
                FactQueryType.MBTI: FactType.MBTI,
                FactQueryType.GOAL: FactType.GOAL,
            }
            resolved = mapping.get(fact_type)
            if resolved:
                return resolved
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "LLM fact query detection failed: %s, falling back to keywords",
            exc,
        )

    return detect_fact_query_keywords(content)


def detect_fact_query_keywords(content: str) -> Optional[FactType]:
    """Keyword fallback for fact query detection."""

    normalized = content.lower().strip().replace("?", "").replace(".", "")
    query_map: Dict[FactType, Iterable[str]] = {
        FactType.USER_NAME: (
            "내 이름",
            "제 이름",
            "내이름",
            "제이름",
            "내 이름이 뭐",
            "이름이 뭐",
            "내 이름 기억",
            "내가 누구",
            "내가 누구야",
        ),
        FactType.JOB: ("내 직업", "제 직업", "직업이 뭐", "무슨 일", "내직업"),
        FactType.MBTI: ("내 mbti", "제 mbti", "mbti가 뭐"),
        FactType.HOBBY: ("내 취미", "제 취미", "취미가 뭐"),
        FactType.GOAL: ("내 목표", "제 목표", "목표가 뭐"),
    }

    for fact_type, keywords in query_map.items():
        if any(keyword in normalized for keyword in keywords):
            return fact_type
    return None


async def build_fact_query_response(
    *,
    content: str,
    user_id: str,
    user_fact_service: UserFactService,
    cache_service: CacheService,
    intent_classifier: IntentClassifierService,
) -> Tuple[Optional[FactType], Optional[str]]:
    """Return a cached fact response if the user asked for one."""

    queried_fact_type = await detect_fact_query(content, intent_classifier)
    if not queried_fact_type:
        return None, None

    cache_key = f"fact_query:{user_id}:{queried_fact_type.value}"
    facts_to_format: List[str] = []

    cached = await maybe_await(cache_service.get(cache_key))
    if cached:
        facts_to_format = cached
    else:
        if queried_fact_type == FactType.USER_NAME:
            profile = await maybe_await(user_fact_service.get_user_profile(user_id))
            if profile and getattr(profile, "name", None):
                facts_to_format = [profile.name]
        else:
            user_facts = await maybe_await(
                user_fact_service.list_facts(
                    user_id=user_id,
                    fact_type=queried_fact_type,
                    latest_only=True,
                )
            )
            if user_facts:
                facts_to_format = [
                    fact.get("content") or fact.get("value")
                    for fact in user_facts
                    if fact.get("content") or fact.get("value")
                ]
        if facts_to_format:
            await maybe_await(
                cache_service.set(cache_key, facts_to_format, ttl=3600)
            )

    ai_content = (
        f"'{queried_fact_type.value}'에 대해 알려주신 정보가 아직 없어요."
    )
    if facts_to_format:
        fact_string = "', '".join(map(str, facts_to_format))
        if queried_fact_type == FactType.USER_NAME:
            ai_content = (
                f"당신의 이름은 '{facts_to_format[0]}'(으)로 기억하고 있어요."
            )
        else:
            ai_content = (
                f"회원님의 '{queried_fact_type.value}' 정보는 '{fact_string}'입니다."
            )

    return queried_fact_type, ai_content


def extract_user_name(text: str) -> Optional[str]:
    """Extract a likely user name from free-form input."""

    if not text or ("이름" not in text and "불러" not in text):
        return None

    for pattern in NAME_EXTRACTION_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        candidate = match.group(1).strip()
        candidate = re.sub(r"[\s,.;!?]+$", "", candidate)

        for suffix in NAME_EXTRACTION_SUFFIXES:
            if candidate.endswith(suffix):
                candidate = candidate[: -len(suffix)]

        candidate = candidate.strip()
        if not candidate or any(char.isdigit() for char in candidate):
            continue
        if len(candidate) < 2 or len(candidate) > 10:
            continue
        return candidate

    return None


async def stream_immediate_response(
    *,
    room_id: str,
    user_id: str,
    storage_service: StorageService,
    content: str,
    memory_service: Optional[MemoryService] = None,
    background_tasks: Optional[BackgroundTaskService] = None,
    realtime_service: Optional[RealtimeService] = None,
) -> EventSourceResponse:
    """Emit a single-message SSE response used by quick intents."""

    ai_message = Message(
        message_id=generate_id(),
        room_id=room_id,
        user_id="ai",
        content=content,
        timestamp=get_current_timestamp(),
        role="ai",
    )
    storage_service.save_message(ai_message)
    if realtime_service:
        await realtime_service.publish(
            room_id, "new_message", ai_message.model_dump()
        )

    if memory_service and background_tasks:
        schedule_context_refresh(
            background_tasks,
            memory_service,
            room_id,
            user_id,
            f"{ai_message.message_id}:immediate",
        )

    async def generator():
        yield {
            "event": "meta",
            "data": RealtimeService.format_event(
                "meta", {"status": "started"}
            ),
        }
        yield {
            "event": "delta",
            "data": RealtimeService.format_event(
                "delta",
                {"delta": content},
                {"chunk_index": 1, "delivery": "immediate"},
            ),
        }
        final_payload = {
            "message_id": ai_message.message_id,
            "meta": {"status": "completed", "chunk_count": 1},
        }
        yield {
            "event": "done",
            "data": RealtimeService.format_event(
                "done",
                final_payload,
                {"chunk_count": 1, "delivery": "immediate"},
            ),
        }

    return EventSourceResponse(generator())


def schedule_context_refresh(
    background_tasks: BackgroundTaskService,
    memory_service: MemoryService,
    room_id: str,
    user_id: str,
    trigger: str,
) -> None:
    """Schedule a context refresh task if possible."""

    task_id = f"context_refresh:{room_id}:{trigger}"
    try:
        background_tasks.create_background_task(
            task_id,
            memory_service.refresh_context,
            room_id,
            user_id,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "Failed to schedule context refresh (task=%s): %s",
            task_id,
            exc,
            exc_info=True,
        )


async def classify_intent(
    intent_service: IntentService, content: str, message_id: str
) -> Tuple[str, Dict[str, Any]]:
    """Classify an intent and ensure a consistent fallback shape."""

    intent = ""
    entities: Dict[str, Any] = {}
    try:
        intent_result = await maybe_await(
            intent_service.classify_intent(content, message_id)
        )
        intent = intent_result.get("intent", "")
        raw_entities = intent_result.get("entities")
        if isinstance(raw_entities, dict):
            entities = raw_entities
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Intent classification failed: %s", exc)
    return intent, entities


async def build_quick_intent_response(
    *,
    intent: str,
    content: str,
    user_id: str,
    entities: Dict[str, Any],
    user_fact_service: UserFactService,
    cache_service: CacheService,
    search_service: ExternalSearchService,
) -> Optional[str]:
    """Handle intents that can return an immediate deterministic answer."""

    if intent == "name_set":
        name_value = ""
        entity_name = entities.get("name") if isinstance(entities, dict) else None
        if isinstance(entity_name, str):
            name_value = entity_name.strip()
        if not name_value:
            name_value = extract_user_name(content) or ""

        if name_value:
            await maybe_await(
                user_fact_service.update_user_profile(
                    user_id, {"name": name_value}
                )
            )
            await maybe_await(
                cache_service.delete(
                    f"fact_query:{user_id}:{FactType.USER_NAME.value}"
                )
            )
            return f"알겠습니다, {name_value}님! 앞으로 그렇게 불러드릴게요."
        return "이름을 정확히 알려주시면 기억해 둘게요."

    if intent == "name_get":
        profile = await maybe_await(user_fact_service.get_user_profile(user_id))
        if profile and getattr(profile, "name", None):
            return f"당신의 이름은 '{profile.name}'으로 기억하고 있어요."
        return "아직 이름을 모르고 있어요. 알려주시면 기억해 둘게요!"

    if intent == "time":
        return search_service.now_kst()

    if intent == "weather":
        location = (
            entities.get("location") if isinstance(entities, dict) else None
        ) or "서울"
        return search_service.weather(location)

    if intent == "wiki":
        topic = (
            entities.get("topic") if isinstance(entities, dict) else None
        ) or "인공지능"
        return await maybe_await(search_service.wiki(topic))

    if intent == "search":
        query = (
            entities.get("query") if isinstance(entities, dict) else None
        ) or "AI"
        items = await maybe_await(search_service.search(query, 3))
        if items:
            lines = [f"🔎 '{query}' 검색 결과:"]
            for index, item in enumerate(items, 1):
                lines.append(
                    f"{index}. {item['title']}\n{item['link']}\n{item['snippet']}"
                )
            return "\n\n".join(lines)
        return f"'{query}'에 대한 검색 결과를 찾을 수 없습니다."

    return None


async def build_fact_query_success_response(
    *,
    room_id: str,
    message: Message,
    ai_content: str,
    storage_service: StorageService,
    realtime_service: RealtimeService,
) -> Dict[str, Any]:
    """Persist a fact query response and return an API payload."""

    ai_message = Message(
        message_id=generate_id(),
        room_id=room_id,
        user_id="ai",
        content=ai_content,
        timestamp=get_current_timestamp(),
        role="ai",
    )
    storage_service.save_message(ai_message)
    maybe_event = ai_message.model_dump()
    # Publish event synchronously to keep SSE clients up-to-date.
    await maybe_await(
        realtime_service.publish(room_id, "new_message", maybe_event)
    )

    return create_success_response(
        data={
            "message": message.model_dump(),
            "ai_response": ai_message.model_dump(),
        }
    )


class MessagePipeline:
    """Orchestrate the classic synchronous message flow."""

    def __init__(
        self,
        *,
        storage_service: StorageService,
        rag_service: RAGService,
        memory_service: MemoryService,
        search_service: ExternalSearchService,
        intent_service: IntentService,
        review_service: ReviewService,
        llm_service: LLMService,
        fact_extractor_service: FactExtractorService,
        user_fact_service: UserFactService,
        cache_service: CacheService,
        background_tasks: BackgroundTaskService,
        realtime_service: RealtimeService,
        intent_classifier: IntentClassifierService,
    ) -> None:
        self.storage_service = storage_service
        self.rag_service = rag_service
        self.memory_service = memory_service
        self.search_service = search_service
        self.intent_service = intent_service
        self.review_service = review_service
        self.llm_service = llm_service
        self.fact_extractor_service = fact_extractor_service
        self.user_fact_service = user_fact_service
        self.cache_service = cache_service
        self.background_tasks = background_tasks
        self.realtime_service = realtime_service
        self.intent_classifier = intent_classifier

    async def process_user_message(
        self,
        *,
        room_id: str,
        user_id: str,
        content: str,
        raw_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persist a user message, generate a reply and return the API payload."""

        message = await self._persist_user_message(
            room_id=room_id,
            user_id=user_id,
            content=content,
        )

        await ensure_fact_extraction(
            message=message,
            user_fact_service=self.user_fact_service,
            fact_extractor_service=self.fact_extractor_service,
            background_tasks=self.background_tasks,
            execute_inline=True,
        )

        _, fact_response = await build_fact_query_response(
            content=content,
            user_id=user_id,
            user_fact_service=self.user_fact_service,
            cache_service=self.cache_service,
            intent_classifier=self.intent_classifier,
        )

        if fact_response:
            return await build_fact_query_success_response(
                room_id=room_id,
                message=message,
                ai_content=fact_response,
                storage_service=self.storage_service,
                realtime_service=self.realtime_service,
            )

        current_room = await self._maybe_get_room(room_id)
        pending_action_key = f"pending_action:{room_id}"
        pending_action_facts = await maybe_await(
            self.memory_service.get_user_facts(
                user_id,
                kind="conversation_state",
                key=pending_action_key,
            )
        )

        intent_from_client = raw_payload.get("intent")

        ai_content = ""
        intent = ""
        entities: Dict[str, Any] = {}

        if pending_action_facts:
            # Legacy pending-action flows are not yet implemented in the pipeline.
            logger.debug(
                "Pending action facts detected for room %s; falling back to default flow.",
                room_id,
            )
        elif intent_from_client:
            intent = intent_from_client
        else:
            intent, entities = await classify_intent(
                self.intent_service,
                content,
                message.message_id,
            )

        quick_response = await build_quick_intent_response(
            intent=intent,
            content=content,
            user_id=user_id,
            entities=entities,
            user_fact_service=self.user_fact_service,
            cache_service=self.cache_service,
            search_service=self.search_service,
        )

        if quick_response is not None:
            ai_content = quick_response
        elif intent == "review":
            ai_content = await self._handle_review_intent(
                current_room=current_room,
                room_id=room_id,
                user_id=user_id,
                content=content,
                trace_id=str(message.message_id),
            )
        elif intent == "start_memory_promotion":
            await maybe_await(
                self.memory_service.upsert_user_fact(
                    user_id,
                    kind="conversation_state",
                    key=pending_action_key,
                    value={"action": "promote_memory_confirmation"},
                    confidence=1.0,
                )
            )
            ai_content = (
                "어떤 대화를 상위 룸으로 올릴까요? '어제 대화 전부' 또는 'AI 윤리에 대한 내용만'과 같이 구체적으로 말씀해주세요."
            )
        else:
            ai_content = await self._generate_rag_response(
                room_id=room_id,
                user_id=user_id,
                content=content,
                message_id=message.message_id,
            )

        ai_message = Message(
            message_id=generate_id(),
            room_id=room_id,
            user_id="ai",
            content=ai_content,
            timestamp=get_current_timestamp(),
            role="ai",
        )
        self.storage_service.save_message(ai_message)
        await self.realtime_service.publish(
            room_id,
            "new_message",
            ai_message.model_dump(),
        )

        suggestion = await self._check_and_suggest_review(
            room_id=room_id,
            user_id=user_id,
        )

        return create_success_response(
            data={
                "message": message.model_dump(),
                "ai_response": ai_message.model_dump(),
                "intent": intent,
                "entities": entities,
                "suggestion": suggestion,
            },
            message="Message sent successfully",
        )

    async def _persist_user_message(
        self,
        *,
        room_id: str,
        user_id: str,
        content: str,
    ) -> Message:
        message = Message(
            message_id=generate_id(),
            room_id=room_id,
            user_id=user_id,
            content=content,
            timestamp=get_current_timestamp(),
        )
        self.storage_service.save_message(message)
        await self.realtime_service.publish(
            room_id,
            "new_message",
            message.model_dump(),
        )
        return message

    async def _maybe_get_room(self, room_id: str):
        return await asyncio.to_thread(self.storage_service.get_room, room_id)

    async def _handle_review_intent(
        self,
        *,
        current_room,
        room_id: str,
        user_id: str,
        content: str,
        trace_id: str,
    ) -> str:
        if not current_room or current_room.type != RoomType.SUB:
            return "검토 기능은 서브룸에서만 시작할 수 있습니다."

        topic = (
            content.replace("검토해보자", "").replace("리뷰해줘", "").strip()
        )
        if not topic:
            topic = f"'{current_room.name}'에 대한 검토"

        return await self._create_review_and_start(
            room_id=room_id,
            user_id=user_id,
            topic=topic,
            trace_id=trace_id,
        )

    async def _generate_rag_response(
        self,
        *,
        room_id: str,
        user_id: str,
        content: str,
        message_id: str,
    ) -> str:
        memory_context = await maybe_await(
            self.memory_service.build_hierarchical_context_blocks(
                room_id=room_id,
                user_id=user_id,
                query=content,
            )
        )
        return await maybe_await(
            self.rag_service.generate_rag_response(
                room_id,
                user_id,
                content,
                memory_context,
                message_id,
            )
        )

    async def _create_review_and_start(
        self,
        *,
        room_id: str,
        user_id: str,
        topic: str,
        trace_id: str,
    ) -> str:
        new_review_room = self.storage_service.create_room(
            room_id=generate_id(),
            name=f"검토: {topic}",
            owner_id=user_id,
            room_type=RoomType.REVIEW,
            parent_id=room_id,
        )
        instruction = (
            "이 주제에 대해 최대 4 라운드에 걸쳐 심도 있게 토론하되, 추가 주장이 없으면 조기에 종료해주세요."
        )
        review_meta = ReviewMeta(
            review_id=new_review_room.room_id,
            room_id=new_review_room.room_id,
            topic=topic,
            instruction=instruction,
            total_rounds=4,
            created_at=get_current_timestamp(),
        )
        self.storage_service.save_review_meta(review_meta)
        await maybe_await(
            self.review_service.start_review_process(
                review_id=new_review_room.room_id,
                review_room_id=new_review_room.room_id,
                topic=topic,
                instruction=instruction,
                panelists=None,
                trace_id=trace_id,
            )
        )
        return (
            f"알겠습니다. '{topic}'에 대한 검토를 시작하겠습니다. '{new_review_room.name}' 룸에서 토론을 확인하세요."
        )

    async def _check_and_suggest_review(
        self,
        *,
        room_id: str,
        user_id: str,
    ) -> Optional[str]:
        # This function currently mirrors the legacy placeholder implementation.
        _ = (room_id, user_id, self.llm_service)
        return None

