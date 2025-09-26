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
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import json

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
from app.config.settings import settings
from app.utils.helpers import (
    create_success_response,
    generate_id,
    get_current_timestamp,
    maybe_await,
)

logger = logging.getLogger(__name__)

FACT_QUERY_CLASSIFIER_TIMEOUT = 0.8


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

    keyword_match = detect_fact_query_keywords(content)
    if keyword_match:
        return keyword_match

    try:
        fact_type = await asyncio.wait_for(
            maybe_await(intent_classifier.get_fact_query_type(content)),
            timeout=FACT_QUERY_CLASSIFIER_TIMEOUT,
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
    except asyncio.TimeoutError:
        logger.warning(
            "Fact query classification timed out; falling back to keyword detection."
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "LLM fact query detection failed: %s, falling back to keywords",
            exc,
        )

    return None


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


@dataclass
class QuickIntentResult:
    content: Optional[str] = None
    tool: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None


async def build_quick_intent_response(
    *,
    intent: str,
    content: str,
    user_id: str,
    entities: Dict[str, Any],
    user_fact_service: UserFactService,
    cache_service: CacheService,
    search_service: ExternalSearchService,
) -> Optional[QuickIntentResult]:
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
            return QuickIntentResult(
                content=f"알겠습니다, {name_value}님! 앞으로 그렇게 불러드릴게요."
            )
        return QuickIntentResult(
            content="이름을 정확히 알려주시면 기억해 둘게요."
        )

    if intent == "name_get":
        profile = await maybe_await(user_fact_service.get_user_profile(user_id))
        if profile and getattr(profile, "name", None):
            return QuickIntentResult(
                content=f"당신의 이름은 '{profile.name}'으로 기억하고 있어요."
            )
        return QuickIntentResult(
            content="아직 이름을 모르고 있어요. 알려주시면 기억해 둘게요!"
        )

    if intent == "time":
        return QuickIntentResult(content=search_service.now_kst())

    if intent == "weather":
        location = (
            entities.get("location") if isinstance(entities, dict) else None
        ) or "서울"
        cache_key = f"weather:{location.lower()}"
        cached_report = await maybe_await(cache_service.get(cache_key))
        weather_report: Optional[Dict[str, Any]] = None
        if cached_report:
            weather_report = cached_report
        else:
            weather_report = await maybe_await(search_service.weather(location))
            if weather_report:
                await maybe_await(
                    cache_service.set(
                        cache_key,
                        weather_report,
                        ttl=settings.WEATHER_CACHE_SECONDS,
                    )
                )

        if not weather_report:
            return QuickIntentResult(
                content=f"'{location}' 날씨 정보를 가져오는 데 실패했어요. 잠시 후 다시 시도해 주세요."
            )

        return QuickIntentResult(
            tool="weather",
            data=weather_report,
            meta={
                "location": location,
                "source": weather_report.get("source"),
            },
        )

    if intent == "wiki":
        topic = (
            entities.get("topic") if isinstance(entities, dict) else None
        ) or "인공지능"
        wiki_summary = await maybe_await(search_service.wiki(topic))
        return QuickIntentResult(content=wiki_summary)

    if intent == "search":
        query = (
            entities.get("query") if isinstance(entities, dict) else None
        ) or "AI"
        items = await maybe_await(search_service.search(query, 3))
        if items:
            return QuickIntentResult(
                tool="search",
                data={"query": query, "results": items},
                meta={"source": "Google Custom Search"},
            )
        return QuickIntentResult(
            content=f"'{query}'에 대한 검색 결과를 찾을 수 없습니다."
        )

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
            self.user_fact_service.list_facts(
                user_id=user_id,
                fact_type=None,
                latest_only=True,
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

        if quick_response is not None and quick_response.content:
            ai_content = quick_response.content
        elif quick_response is not None and quick_response.tool:
            ai_content = await self._compose_tool_based_response(
                room_id=room_id,
                message_id=str(message.message_id),
                user_message=content,
                tool_name=quick_response.tool,
                tool_payload=quick_response.data or {},
                tool_metadata=quick_response.meta or {},
            )
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

    async def _prepare_memory_context(
        self,
        *,
        room_id: str,
        user_id: str,
        content: str,
    ) -> List[Dict[str, Any]]:
        limit = getattr(settings, "HYBRID_RETURN_TOPN", 5)
        hierarchical_task = asyncio.create_task(
            maybe_await(
                self.memory_service.build_hierarchical_context_blocks(
                    room_id=room_id,
                    user_id=user_id,
                    query=content,
                    limit=limit,
                )
            )
        )
        fallback_task = asyncio.create_task(
            maybe_await(self.memory_service.get_context(room_id, user_id))
        )

        hierarchical_context, fallback_context = await asyncio.gather(
            hierarchical_task,
            fallback_task,
            return_exceptions=True,
        )

        if isinstance(hierarchical_context, Exception):
            logger.warning(
                "Failed to build hierarchical context blocks (room=%s, user=%s): %s",
                room_id,
                user_id,
                hierarchical_context,
                exc_info=True,
            )
            hierarchical_context = []

        if isinstance(fallback_context, Exception):
            logger.debug(
                "Fallback memory context lookup failed (room=%s, user=%s): %s",
                room_id,
                user_id,
                fallback_context,
                exc_info=True,
            )
            fallback_context = []

        if hierarchical_context:
            return hierarchical_context
        if fallback_context:
            return fallback_context
        return []

    async def _stream_rag_response(
        self,
        *,
        room_id: str,
        user_id: str,
        content: str,
        message_id: str,
        memory_context: List[Dict[str, Any]],
    ) -> str:
        await self.realtime_service.publish(
            room_id,
            "meta",
            {"status": "started"},
            meta={"message_id": message_id, "delivery": "sync_pipeline"},
        )

        aggregated_chunks: List[str] = []
        chunk_index = 0

        try:
            stream = self.rag_service.generate_rag_response_stream(
                room_id=room_id,
                user_id=user_id,
                user_message=content,
                memory_context=memory_context,
                message_id=message_id,
            )

            async for chunk in stream:
                if isinstance(chunk, dict):
                    delta = chunk.get("delta")
                    meta_payload = chunk.get("meta")
                else:
                    delta = str(chunk)
                    meta_payload = None

                if meta_payload:
                    await self.realtime_service.publish(
                        room_id,
                        "meta",
                        meta_payload,
                        meta={"message_id": message_id, "delivery": "sync_pipeline", **meta_payload},
                    )

                if delta:
                    chunk_index += 1
                    aggregated_chunks.append(delta)
                    await self.realtime_service.publish(
                        room_id,
                        "delta",
                        {"delta": delta},
                        meta={
                            "message_id": message_id,
                            "chunk_index": chunk_index,
                            "delivery": "sync_pipeline",
                        },
                    )
        except Exception as stream_error:
            logger.error(
                "Error during streaming response for room %s (user=%s): %s",
                room_id,
                user_id,
                stream_error,
                exc_info=True,
            )
            await self.realtime_service.publish(
                room_id,
                "done",
                {
                    "message_id": message_id,
                    "status": "failed",
                    "error": "응답 생성 중 오류가 발생했습니다.",
                },
                meta={"message_id": message_id, "delivery": "sync_pipeline", "status": "failed"},
            )
            return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

        final_text = "".join(aggregated_chunks)
        await self.realtime_service.publish(
            room_id,
            "done",
            {"message_id": message_id, "status": "completed", "chunk_count": chunk_index},
            meta={
                "message_id": message_id,
                "delivery": "sync_pipeline",
                "status": "completed",
                "chunk_count": chunk_index,
            },
        )
        return final_text or ""

    async def _generate_rag_response(
        self,
        *,
        room_id: str,
        user_id: str,
        content: str,
        message_id: str,
    ) -> str:
        memory_context = await self._prepare_memory_context(
            room_id=room_id,
            user_id=user_id,
            content=content,
        )
        response = await self._stream_rag_response(
            room_id=room_id,
            user_id=user_id,
            content=content,
            message_id=message_id,
            memory_context=memory_context,
        )
        return response

    async def _compose_tool_based_response(
        self,
        *,
        room_id: str,
        message_id: str,
        user_message: str,
        tool_name: str,
        tool_payload: Dict[str, Any],
        tool_metadata: Dict[str, Any],
    ) -> str:
        location_hint = tool_metadata.get("location") or tool_payload.get("location")
        start_detail = (
            f"{location_hint}의 실시간 데이터를 확인하고 있어요."
            if location_hint
            else "실시간 데이터를 확인하고 있어요."
        )
        await self.realtime_service.publish(
            room_id,
            "meta",
            {
                "status": "tool_start",
                "tool": tool_name,
                "detail": start_detail,
            },
            meta={"message_id": message_id, "tool": tool_name, "stage": "start"},
        )

        await self.realtime_service.publish(
            room_id,
            "meta",
            {
                "status": "tool_data_ready",
                "tool": tool_name,
                "detail": "데이터 수집이 완료되었습니다. 답변을 정리하고 있어요.",
            },
            meta={"message_id": message_id, "tool": tool_name, "stage": "data_ready"},
        )

        provider_name, model_name, routing_reason = self.llm_service.select_model_for_task(
            task=tool_name,
            intent=tool_name,
            metadata={**tool_metadata, "tool": tool_name},
        )

        system_prompt = (
            "당신은 Origin이라는 AI 어시스턴트입니다. "
            "사용자에게 따뜻하지만 전문적인 어조로 한국어 답변을 제공하세요. "
            "도구에서 전달된 사실을 중심으로 핵심 정보를 구조화하고, "
            "불확실한 값은 추정임을 밝히며 대안을 제시합니다. "
            "응답 마지막에 `참고:` 라인을 추가해 사용한 데이터 출처나 기준을 요약하세요."
        )

        tool_json = json.dumps(tool_payload, ensure_ascii=False, indent=2)
        metadata_json = (
            json.dumps(tool_metadata, ensure_ascii=False, indent=2)
            if tool_metadata
            else "{}"
        )

        user_prompt_parts = [
            f"사용자 질문:\n{user_message}",
            f"도구 '{tool_name}' 결과(JSON):\n{tool_json}",
            f"추가 메타데이터:\n{metadata_json}",
            "위 정보를 기반으로 다음을 수행하세요:",
            "1. 가장 중요한 사실 두세 가지를 우선 설명합니다.",
            "2. 사용자가 바로 활용할 수 있는 조언이나 맥락을 덧붙입니다.",
            "3. 모호하거나 데이터가 부족하면 그 이유와 대안을 안내합니다.",
            "4. 마지막 줄에 `참고:` 형식으로 데이터 출처나 기준을 요약합니다.",
        ]
        user_prompt = "\n\n".join(user_prompt_parts)

        try:
            response_text, _ = await self.llm_service.invoke(
                model=model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                request_id=message_id,
                provider_name=provider_name,
            )
        except Exception as exc:
            logger.error(
                "Failed to summarize %s tool output for message %s: %s",
                tool_name,
                message_id,
                exc,
                exc_info=True,
            )
            await self.realtime_service.publish(
                room_id,
                "meta",
                {
                    "status": "tool_failed",
                    "tool": tool_name,
                    "detail": "도구 결과를 요약하는 중 오류가 발생했습니다.",
                },
                meta={"message_id": message_id, "tool": tool_name, "stage": "failed"},
            )
            return "도구 결과를 요약하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

        reference_tokens: List[str] = []
        for value in [
            tool_payload.get("source"),
            tool_metadata.get("source"),
            tool_metadata.get("location"),
        ]:
            if isinstance(value, str) and value:
                reference_tokens.append(value)

        if reference_tokens:
            deduped = list(dict.fromkeys(reference_tokens))
            reference_line = "참고: " + ", ".join(deduped)
            if reference_line not in (response_text or ""):
                response_text = f"{(response_text or '').strip()}\n\n{reference_line}".strip()

        await self.realtime_service.publish(
            room_id,
            "meta",
            {
                "status": "tool_complete",
                "tool": tool_name,
                "detail": f"{tool_name} 데이터를 바탕으로 답변을 마쳤어요.",
                "routing_reason": routing_reason,
            },
            meta={
                "message_id": message_id,
                "tool": tool_name,
                "stage": "complete",
                "routing_reason": routing_reason,
            },
        )

        return response_text or ""

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
            completed_at=0,
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
