"""Shared helpers for orchestrating message workflows.

This module centralizes reusable pieces of the message routing logic so that
FastAPI route handlers stay focused on transport concerns while the actual
processing happens in well scoped helpers.  The functions defined here are
imported by both the REST and streaming endpoints.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sse_starlette.sse import EventSourceResponse

from app.models.schemas import Message
from app.services.background_task_service import BackgroundTaskService
from app.services.cache_service import CacheService
from app.services.external_api_service import ExternalSearchService
from app.services.fact_extractor_service import FactExtractorService
from app.services.intent_classifier_service import (
    FactQueryType,
    IntentClassifierService,
)
from app.services.intent_service import IntentService
from app.services.memory_service import MemoryService
from app.services.realtime_service import RealtimeService
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

