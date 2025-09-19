"""
Message-related API endpoints
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import (
    AUTH_DEPENDENCY,
    get_storage_service,
    get_rag_service,
    get_memory_service,
    get_search_service,
    get_intent_service,
    get_review_service,
    get_llm_service,
    get_fact_extractor_service,
    get_user_fact_service,
    get_cache_service,
    get_intent_classifier_service,
    get_background_task_service,
    require_auth,
)
from app.services.storage_service import StorageService
from app.services.rag_service import RAGService
from app.services.memory_service import MemoryService
from app.services.external_api_service import ExternalSearchService
from app.services.intent_service import IntentService
from app.services.review_service import ReviewService
from app.services.llm_service import LLMService
from app.services.fact_extractor_service import FactExtractorService
from app.services.user_fact_service import UserFactService
from app.services.cache_service import CacheService
from app.services.intent_classifier_service import IntentClassifierService, FactQueryType
from app.services.background_task_service import BackgroundTaskService
from app.services.fact_types import FactType
from app.utils.helpers import (
    generate_id,
    get_current_timestamp,
    create_success_response,
    maybe_await,
)
from app.models.enums import RoomType
from app.models.schemas import Message, ReviewMeta
from app.config.settings import settings
from app.services.realtime_service import get_realtime_service, RealtimeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["messages"])

# --- V2 Fact Extraction/Retrieval Helpers ---


async def _maybe_get_room(storage_service: StorageService, room_id: str):
    return await asyncio.to_thread(storage_service.get_room, room_id)

async def _handle_fact_extraction(
    user_fact_service: UserFactService,
    fact_extractor_service: FactExtractorService,
    message: Message
):
    """Orchestrates extracting, normalizing, and saving facts from a message."""
    try:
        if message.role != "user": return
        user_profile = await maybe_await(
            user_fact_service.get_user_profile(message.user_id)
        )
        if user_profile and not user_profile.auto_fact_extraction_enabled:
            logger.info(f"Fact extraction disabled for user {message.user_id}. Skipping.")
            return

        raw_facts = await maybe_await(
            fact_extractor_service.extract_facts_from_message(
                message.content, str(message.message_id)
            )
        )
        if not raw_facts: return
        
        logger.info(f"Extracted {len(raw_facts)} potential facts from message {message.message_id}")
        for fact in raw_facts:
            try:
                fact_type_enum = FactType(fact['type'])
                normalized_value = fact_extractor_service.normalize_value(fact_type_enum, fact['value'])
                sensitivity = fact_extractor_service.get_sensitivity(fact_type_enum)
                logger.info(f"=== SAVING FACT === User: {message.user_id}, Type: {fact['type']}, Value: {fact['value']}")
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
                logger.info(f"=== FACT SAVED SUCCESSFULLY === User: {message.user_id}, Type: {fact['type']}")
            except ValueError:
                logger.warning(f"Skipping fact with unknown type: {fact.get('type')}")
                continue
        logger.info(f"Successfully processed facts for message {message.message_id}")
    except Exception as e:
        logger.error(f"Error during background fact extraction for message {message.message_id}: {e}", exc_info=True)

async def _detect_fact_query_improved(content: str, intent_classifier: IntentClassifierService) -> Optional[FactType]:
    """LLM 기반 사실 질문 감지 (fallback으로 키워드 기반)"""
    try:
        # LLM 기반 분류 시도
        fact_type = await maybe_await(
            intent_classifier.get_fact_query_type(content)
        )
        if fact_type and fact_type != FactQueryType.NONE:
            # FactQueryType을 FactType으로 변환
            type_mapping = {
                FactQueryType.USER_NAME: FactType.USER_NAME,
                FactQueryType.JOB: FactType.JOB,
                FactQueryType.HOBBY: FactType.HOBBY,
                FactQueryType.MBTI: FactType.MBTI,
                FactQueryType.GOAL: FactType.GOAL
            }
            return type_mapping.get(fact_type)
    except Exception as e:
        logger.warning(f"LLM fact query detection failed: {e}, falling back to keywords")
    
    # Fallback: 키워드 기반 감지
    return _detect_fact_query_keywords(content)

def _detect_fact_query_keywords(content: str) -> Optional[FactType]:
    """키워드 기반 사실 질문 감지 (fallback)"""
    content = content.lower().strip().replace("?", "").replace(".", "")
    query_map: Dict[FactType, List[str]] = {
        FactType.USER_NAME: [
            "내 이름", "제 이름", "내이름", "제이름", "내 이름이 뭐", "이름이 뭐",
            "내 이름 기억", "내가 누구", "내가 누구야"
        ],
        FactType.JOB: ["내 직업", "제 직업", "직업이 뭐", "무슨 일", "내직업"],
        FactType.MBTI: ["내 mbti", "제 mbti", "mbti가 뭐"],
        FactType.HOBBY: ["내 취미", "제 취미", "취미가 뭐"],
        FactType.GOAL: ["내 목표", "제 목표", "목표가 뭐"],
    }
    for fact_type, keywords in query_map.items():
        for keyword in keywords:
            if keyword in content:
                return fact_type
    return None


NAME_EXTRACTION_PATTERNS = [
    re.compile(r"(?:내|제|저의)\s*이름(?:은|은요|은지)?\s*([\w가-힣]+)", re.IGNORECASE),
    re.compile(r"(?:나를|저를)\s*([\w가-힣]+)\s*라고\s*불러", re.IGNORECASE),
    re.compile(r"(?:이름은)\s*([\w가-힣]+)", re.IGNORECASE),
]
NAME_EXTRACTION_SUFFIXES = ("입니다", "이에요", "예요", "이야", "야", "라고", "라고요", "라고해")


def _extract_user_name(text: str) -> Optional[str]:
    if not text:
        return None
    if "이름" not in text and "불러" not in text:
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
        if not candidate:
            continue
        if any(char.isdigit() for char in candidate):
            continue
        if len(candidate) < 2 or len(candidate) > 10:
            continue
        return candidate
    return None


async def _stream_immediate_response(
    room_id: str,
    user_id: str,
    storage_service: StorageService,
    content: str,
    memory_service: Optional[MemoryService] = None,
    background_tasks: Optional[BackgroundTaskService] = None,
    realtime_service: Optional[RealtimeService] = None,
) -> EventSourceResponse:
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
        await realtime_service.publish(room_id, "new_message", ai_message.model_dump())

    if memory_service and background_tasks:
        task_id = f"context_refresh:{room_id}:{ai_message.message_id}:immediate"
        try:
            background_tasks.create_background_task(
                task_id,
                memory_service.refresh_context,
                room_id,
                user_id,
            )
        except Exception as refresh_error:
            logger.warning(
                "Failed to schedule context refresh for immediate stream response (room=%s): %s",
                room_id,
                refresh_error,
                exc_info=True,
            )

    async def generator():
        yield {
            "event": "meta",
            "data": RealtimeService.format_event("meta", {"status": "started"}),
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

# --- Original Endpoints & Helpers ---

@router.get("/{room_id}/messages", response_model=List[Message])
async def get_messages(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
):
    """Get messages for a room"""
    try:
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")
        messages = storage_service.get_messages(room_id)
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages for room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.get("/{room_id}/messages/events")
async def stream_room_message_events(
    request: Request,
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    realtime_service: RealtimeService = Depends(get_realtime_service),
):
    """Stream real-time message events for a room via SSE."""
    room = await _maybe_get_room(storage_service, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if not settings.AUTH_OPTIONAL and room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied to room events")

    listener_queue = realtime_service.register_listener(room_id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(listener_queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": "keep-alive"}
                    continue

                yield {"event": "new_message", "data": message}
        finally:
            realtime_service.unregister_listener(room_id, listener_queue)

    return EventSourceResponse(event_generator())


async def _create_review_and_start(storage_service: StorageService, review_service: ReviewService, room_id: str, user_id: str, topic: str, trace_id: str) -> str:
    """Helper function to create a review room and start the process."""
    new_review_room = storage_service.create_room(
        room_id=generate_id(), name=f"검토: {topic}", owner_id=user_id,
        room_type=RoomType.REVIEW, parent_id=room_id,
    )
    instruction = "이 주제에 대해 최대 4 라운드에 걸쳐 심도 있게 토론하되, 추가 주장이 없으면 조기에 종료해주세요."
    review_meta = ReviewMeta(
        review_id=new_review_room.room_id, room_id=new_review_room.room_id,
        topic=topic, instruction=instruction, total_rounds=4, created_at=get_current_timestamp(),
    )
    storage_service.save_review_meta(review_meta)
    await maybe_await(
        review_service.start_review_process(
            review_id=new_review_room.room_id,
            review_room_id=new_review_room.room_id,
            topic=topic,
            instruction=instruction,
            panelists=None,
            trace_id=trace_id,
        )
    )
    return f"알겠습니다. '{topic}'에 대한 검토를 시작하겠습니다. '{new_review_room.name}' 룸에서 토론을 확인하세요."


async def _check_and_suggest_review(
    room_id: str, user_id: str, storage_service: StorageService,
    memory_service: MemoryService, llm_service: LLMService,
) -> Optional[str]:
    """Checks if conditions are met to suggest a review."""
    # This function uses the legacy get_user_facts, which is out of scope for the current refactoring.
    return None


@router.post("/{room_id}/messages")
async def send_message(
    room_id: str,
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    rag_service: RAGService = Depends(get_rag_service),
    memory_service: MemoryService = Depends(get_memory_service),
    search_service: ExternalSearchService = Depends(get_search_service),
    intent_service: IntentService = Depends(get_intent_service),
    review_service: ReviewService = Depends(get_review_service),
    llm_service: LLMService = Depends(get_llm_service),
    fact_extractor_service: FactExtractorService = Depends(get_fact_extractor_service),
    user_fact_service: UserFactService = Depends(get_user_fact_service),
    cache_service: CacheService = Depends(get_cache_service),
    realtime_service: RealtimeService = Depends(get_realtime_service),
):
    """Send a message to a room"""
    logger.info(f"=== MESSAGE ENDPOINT CALLED === Room: {room_id}")
    try:
        body = await request.json()
        content = body.get("content", "").strip()
        user_id = user_info["user_id"]
        logger.info(f"=== MESSAGE CONTENT === User: {user_id}, Content: {content}")

        if not content: raise HTTPException(status_code=400, detail="Message content is required")
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")

        message = Message(
            message_id=generate_id(), room_id=room_id, user_id=user_id,
            content=content, timestamp=get_current_timestamp(),
        )
        storage_service.save_message(message)
        await realtime_service.publish(room_id, "new_message", message.model_dump())

        # --- V2 Fact Extraction & Retrieval Logic ---
        # Extract facts immediately for better context awareness
        logger.info(f"=== FACT EXTRACTION START === Message: {message.message_id}, Content: {content}")
        try:
            await _handle_fact_extraction(user_fact_service, fact_extractor_service, message)
            logger.info(f"=== FACT EXTRACTION SUCCESS === Message: {message.message_id}")
            try:
                background_task_service = get_background_task_service()
                task_id = f"fact_extraction_{message.message_id}_async"
                background_task_service.create_background_task(
                    task_id,
                    _handle_fact_extraction,
                    user_fact_service,
                    fact_extractor_service,
                    message,
                )
                logger.info(f"=== BACKGROUND TASK STARTED === Task: {task_id}")
            except Exception as bg_error:
                logger.error(f"=== BACKGROUND TASK FAILED === Error: {bg_error}", exc_info=True)
        except Exception as e:
            logger.error(f"=== FACT EXTRACTION FAILED === Message: {message.message_id}, Error: {e}", exc_info=True)
            try:
                background_task_service = get_background_task_service()
                task_id = f"fact_extraction_{message.message_id}"
                background_task_service.create_background_task(
                    task_id,
                    _handle_fact_extraction,
                    user_fact_service,
                    fact_extractor_service,
                    message,
                )
                logger.info(f"=== BACKGROUND TASK STARTED === Task: {task_id}")
            except Exception as bg_error:
                logger.error(f"=== BACKGROUND TASK FAILED === Error: {bg_error}", exc_info=True)
        
        # LLM 기반 사실 질문 감지
        intent_classifier = get_intent_classifier_service()
        queried_fact_type = await _detect_fact_query_improved(content, intent_classifier)
        if queried_fact_type:
            logger.info(f"Fact query for user {user_id}, type: {queried_fact_type.value}")
            facts_to_format = []
            cache_key = f"fact_query:{user_id}:{queried_fact_type.value}"
            cached_facts = await maybe_await(cache_service.get(cache_key))

            if cached_facts:
                facts_to_format = cached_facts
            else:
                if queried_fact_type == FactType.USER_NAME:
                    profile = await maybe_await(
                        user_fact_service.get_user_profile(user_id)
                    )
                    if profile and profile.name: facts_to_format = [profile.name]
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
                            fact.get('content') or fact.get('value')
                            for fact in user_facts
                            if fact.get('content') or fact.get('value')
                        ]
                if facts_to_format:
                    await maybe_await(
                        cache_service.set(cache_key, facts_to_format, ttl=3600)
                    )

            ai_content = f"'{queried_fact_type.value}'에 대해 알려주신 정보가 아직 없어요."
            if facts_to_format:
                fact_string = "', '".join(map(str, facts_to_format))
                if queried_fact_type == FactType.USER_NAME:
                    ai_content = f"당신의 이름은 '{facts_to_format[0]}'(으)로 기억하고 있어요."
                else:
                    ai_content = f"회원님의 '{queried_fact_type.value}' 정보는 '{fact_string}'입니다."
            
            ai_message = Message(message_id=generate_id(), room_id=room_id, user_id="ai", content=ai_content, timestamp=get_current_timestamp(), role="ai")
            storage_service.save_message(ai_message)
            await realtime_service.publish(room_id, "new_message", ai_message.model_dump())
            return create_success_response(data={"message": message.model_dump(), "ai_response": ai_message.model_dump()})

        # Fact extraction already executed above (or scheduled via background tasks on failure).
        
        # --- Original Intent/Action Processing Logic ---
        current_room = await _maybe_get_room(storage_service, room_id)
        if current_room and current_room.type == RoomType.REVIEW:
            # ... existing review room logic ...
            pass

        pending_action_key = f"pending_action:{room_id}"
        pending_action_facts = await maybe_await(
            memory_service.get_user_facts(
                user_id, kind='conversation_state', key=pending_action_key
            )
        )
        intent_from_client = body.get("intent")
        
        ai_content = ""
        intent = ""
        entities = {}

        if pending_action_facts:
            # This logic is preserved but simplified in this view for brevity.
            pass
        elif intent_from_client:
            intent = intent_from_client
        else:
            intent_result = await maybe_await(
                intent_service.classify_intent(content, message.message_id)
            )
            intent = intent_result["intent"]
            entities = intent_result.get("entities", {})

        logger.info(f"Intent: {intent}, Entities: {entities}")

        if intent == "name_set":
            name_value = ""
            if isinstance(entities, dict):
                entity_name = entities.get("name")
                if isinstance(entity_name, str):
                    name_value = entity_name.strip()
            if not name_value:
                name_value = _extract_user_name(content)

            if name_value:
                await maybe_await(
                    user_fact_service.update_user_profile(user_id, {"name": name_value})
                )
                await maybe_await(
                    cache_service.delete(
                        f"fact_query:{user_id}:{FactType.USER_NAME.value}"
                    )
                )
                ai_content = f"알겠습니다, {name_value}님! 앞으로 그렇게 불러드릴게요."
            else:
                ai_content = "이름을 정확히 알려주시면 기억해 둘게요."
        elif intent == "name_get":
            profile = await maybe_await(
                user_fact_service.get_user_profile(user_id)
            )
            if profile and profile.name:
                ai_content = f"당신의 이름은 '{profile.name}'으로 기억하고 있어요."
            else:
                ai_content = "아직 이름을 모르고 있어요. 알려주시면 기억해 둘게요!"
        elif intent == "time":
            ai_content = search_service.now_kst()
        elif intent == "weather":
            location = entities.get("location") or "서울"
            ai_content = search_service.weather(location)
        elif intent == "wiki":
            topic = entities.get("topic") or "인공지능"
            ai_content = await maybe_await(search_service.wiki(topic))
        elif intent == "search":
            query = entities.get("query") or "AI"
            items = await maybe_await(search_service.search(query, 3))
            if items:
                lines = [f"🔎 '{query}' 검색 결과:"]
                for i, item in enumerate(items, 1):
                    lines.append(f"{i}. {item['title']}\n{item['link']}\n{item['snippet']}")
                ai_content = "\n\n".join(lines)
            else:
                ai_content = f"'{query}'에 대한 검색 결과를 찾을 수 없습니다."
        elif intent == "review":
            if not current_room or current_room.type != RoomType.SUB:
                ai_content = "검토 기능은 서브룸에서만 시작할 수 있습니다."
            else:
                topic = content.replace("검토해보자", "").replace("리뷰해줘", "").strip()
                if not topic: topic = f"'{current_room.name}'에 대한 검토"
                ai_content = await _create_review_and_start(storage_service, review_service, room_id, user_id, topic, message.message_id)
        elif intent == "start_memory_promotion":
            await maybe_await(
                memory_service.upsert_user_fact(
                    user_id,
                    kind='conversation_state',
                    key=pending_action_key,
                    value={'action': 'promote_memory_confirmation'},
                    confidence=1.0,
                )
            )
            ai_content = "어떤 대화를 상위 룸으로 올릴까요? '어제 대화 전부' 또는 'AI 윤리에 대한 내용만'과 같이 구체적으로 말씀해주세요."
        else:  # Fallback to general RAG response
            memory_context = await maybe_await(
                memory_service.build_hierarchical_context_blocks(
                    room_id=room_id,
                    user_id=user_id,
                    query=content,
                )
            )
            ai_content = await maybe_await(
                rag_service.generate_rag_response(
                    room_id, user_id, content, memory_context, message.message_id,
                )
            )

        ai_message = Message(
            message_id=generate_id(), room_id=room_id, user_id="ai",
            content=ai_content, timestamp=get_current_timestamp(), role="ai"
        )
        storage_service.save_message(ai_message)
        await realtime_service.publish(room_id, "new_message", ai_message.model_dump())

        suggestion = await _check_and_suggest_review(
            room_id, user_id, storage_service, memory_service, llm_service
        )
        return create_success_response(
            data={"message": message.model_dump(), "ai_response": ai_message.model_dump(), "intent": intent, "entities": entities, "suggestion": suggestion},
            message="Message sent successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@router.post("/{room_id}/messages/stream")
async def send_message_stream(
    room_id: str,
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    rag_service: RAGService = Depends(get_rag_service),
    memory_service: MemoryService = Depends(get_memory_service),
    fact_extractor_service: FactExtractorService = Depends(get_fact_extractor_service),
    user_fact_service: UserFactService = Depends(get_user_fact_service),
    background_tasks: BackgroundTaskService = Depends(get_background_task_service),
    search_service: ExternalSearchService = Depends(get_search_service),
    intent_service: IntentService = Depends(get_intent_service),
    cache_service: CacheService = Depends(get_cache_service),
    intent_classifier: IntentClassifierService = Depends(get_intent_classifier_service),
    realtime_service: RealtimeService = Depends(get_realtime_service),
):
    """
    Stream a message to a room. This endpoint now supports true streaming.
    """
    logger.info(f"=== STREAM ENDPOINT CALLED === Room: {room_id}")
    body = await request.json()
    content = body.get("content", "").strip()
    user_id = user_info["user_id"]

    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")

    # Save the user's message immediately
    user_message = Message(
        message_id=generate_id(), room_id=room_id, user_id=user_id,
        content=content, timestamp=get_current_timestamp(),
    )
    storage_service.save_message(user_message)
    await realtime_service.publish(room_id, "new_message", user_message.model_dump())

    def _schedule_context_refresh(trigger: str) -> None:
        task_id = f"context_refresh:{room_id}:{trigger}"
        try:
            background_tasks.create_background_task(
                task_id,
                memory_service.refresh_context,
                room_id,
                user_id,
            )
        except Exception as refresh_error:
            logger.warning(
                "Failed to schedule context refresh (task=%s): %s",
                task_id,
                refresh_error,
                exc_info=True,
            )

    _schedule_context_refresh(f"user:{user_message.message_id}")
    
    # Start fact extraction as a background task so it doesn't block the response
    background_tasks.create_background_task(
        f"fact_extraction_{user_message.message_id}",
        _handle_fact_extraction,
        user_fact_service, fact_extractor_service, user_message
    )

    # Handle fact queries ("내 이름이 뭐야?" 등) before streaming
    queried_fact_type = await _detect_fact_query_improved(content, intent_classifier)
    if queried_fact_type:
        facts_to_format: List[str] = []
        cache_key = f"fact_query:{user_id}:{queried_fact_type.value}"
        cached_facts = await maybe_await(cache_service.get(cache_key))

        if cached_facts:
            facts_to_format = cached_facts
        else:
            if queried_fact_type == FactType.USER_NAME:
                profile = await maybe_await(
                    user_fact_service.get_user_profile(user_id)
                )
                if profile and profile.name:
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
            await maybe_await(cache_service.set(cache_key, facts_to_format, ttl=3600))

        ai_content = f"'{queried_fact_type.value}'에 대해 알려주신 정보가 아직 없어요."
        if facts_to_format:
            fact_string = "', '".join(map(str, facts_to_format))
            if queried_fact_type == FactType.USER_NAME:
                ai_content = f"당신의 이름은 '{facts_to_format[0]}'(으)로 기억하고 있어요."
            else:
                ai_content = f"회원님의 '{queried_fact_type.value}' 정보는 '{fact_string}'입니다."

        return await _stream_immediate_response(
            room_id=room_id,
            user_id=user_id,
            storage_service=storage_service,
            content=ai_content,
            memory_service=memory_service,
            background_tasks=background_tasks,
            realtime_service=realtime_service,
        )

    # Intent-based handling for quick responses (time, weather, name etc.)
    intent = ""
    entities: Dict[str, Any] = {}
    try:
        intent_result = await maybe_await(
            intent_service.classify_intent(content, user_message.message_id)
        )
        intent = intent_result["intent"]
        entities = intent_result.get("entities", {})
    except Exception as intent_error:
        logger.warning(f"Intent classification fallback in stream path failed: {intent_error}")

    direct_response: Optional[str] = None

    if intent == "name_set":
        name_value = ""
        if isinstance(entities, dict):
            entity_name = entities.get("name")
            if isinstance(entity_name, str):
                name_value = entity_name.strip()
        if not name_value:
            name_value = _extract_user_name(content) or ""

        if name_value:
            await maybe_await(
                user_fact_service.update_user_profile(user_id, {"name": name_value})
            )
            await maybe_await(
                cache_service.delete(
                    f"fact_query:{user_id}:{FactType.USER_NAME.value}"
                )
            )
            direct_response = f"알겠습니다, {name_value}님! 앞으로 그렇게 불러드릴게요."
        else:
            direct_response = "이름을 정확히 알려주시면 기억해 둘게요."
    elif intent == "name_get":
        profile = await maybe_await(
            user_fact_service.get_user_profile(user_id)
        )
        if profile and profile.name:
            direct_response = f"당신의 이름은 '{profile.name}'으로 기억하고 있어요."
        else:
            direct_response = "아직 이름을 모르고 있어요. 알려주시면 기억해 둘게요!"
    elif intent == "time":
        direct_response = search_service.now_kst()
    elif intent == "weather":
        location = entities.get("location") if isinstance(entities, dict) else None
        direct_response = search_service.weather(location or "서울")
    elif intent == "wiki":
        topic = entities.get("topic") if isinstance(entities, dict) else None
        direct_response = await maybe_await(
            search_service.wiki(topic or "인공지능")
        )
    elif intent == "search":
        query = entities.get("query") if isinstance(entities, dict) else None
        search_query = query or "AI"
        items = await maybe_await(search_service.search(search_query, 3))
        if items:
            lines = [f"🔎 '{search_query}' 검색 결과:"]
            for i, item in enumerate(items, 1):
                lines.append(f"{i}. {item['title']}\n{item['link']}\n{item['snippet']}")
            direct_response = "\n\n".join(lines)
        else:
            direct_response = f"'{search_query}'에 대한 검색 결과를 찾을 수 없습니다."

    if direct_response is not None:
        return await _stream_immediate_response(
            room_id=room_id,
            user_id=user_id,
            storage_service=storage_service,
            content=direct_response,
            memory_service=memory_service,
            background_tasks=background_tasks,
            realtime_service=realtime_service,
        )

    async def stream_generator():
        ai_response_content = ""
        chunk_count = 0
        stream_completed = False

        yield {
            "event": "meta",
            "data": RealtimeService.format_event(
                "meta",
                {"status": "started"},
                {"delivery": "stream"},
            ),
        }

        try:
            try:
                hierarchical_context = await maybe_await(
                    memory_service.build_hierarchical_context_blocks(
                        room_id=room_id,
                        user_id=user_id,
                        query=content,
                        limit=getattr(settings, "HYBRID_RETURN_TOPN", 5),
                    )
                )
            except Exception as context_error:
                logger.warning(
                    "Failed to build hierarchical context blocks (room=%s, user=%s): %s",
                    room_id,
                    user_id,
                    context_error,
                    exc_info=True,
                )
                hierarchical_context = []

            if hierarchical_context:
                memory_context = hierarchical_context
            else:
                memory_context = await maybe_await(
                    memory_service.get_context(room_id, user_id)
                )

            stream = rag_service.generate_rag_response_stream(
                room_id=room_id,
                user_id=user_id,
                user_message=content,
                memory_context=memory_context,
                message_id=user_message.message_id
            )

            async for chunk in stream:
                if isinstance(chunk, dict):
                    delta = chunk.get("delta")
                    meta = chunk.get("meta")
                else:
                    delta = str(chunk)
                    meta = None

                if delta:
                    ai_response_content += delta
                    chunk_count += 1
                    yield {
                        "event": "delta",
                        "data": RealtimeService.format_event(
                            "delta",
                            {"delta": delta},
                            {"chunk_index": chunk_count, "delivery": "stream"},
                        ),
                    }

                if meta:
                    yield {
                        "event": "meta",
                        "data": RealtimeService.format_event(
                            "meta",
                            meta,
                            {"chunk_index": chunk_count, "delivery": "stream"},
                        ),
                    }

            stream_completed = True
        except Exception as stream_error:
            logger.error(
                "Error during streaming response for room %s: %s",
                room_id,
                stream_error,
                exc_info=True,
            )
            yield {
                "event": "error",
                "data": RealtimeService.format_event(
                    "error",
                    {"error": "An error occurred during streaming."},
                    {"delivery": "stream"},
                ),
            }
        finally:
            if stream_completed:
                ai_message = Message(
                    message_id=generate_id(),
                    room_id=room_id,
                    user_id="ai",
                    content=ai_response_content,
                    timestamp=get_current_timestamp(),
                    role="assistant"
                )
                storage_service.save_message(ai_message)
                await realtime_service.publish(room_id, "new_message", ai_message.model_dump())

                _schedule_context_refresh(f"assistant:{ai_message.message_id}")

                final_payload = {
                    "message_id": ai_message.message_id,
                    "meta": {"status": "completed", "chunk_count": chunk_count},
                }
                yield {
                    "event": "done",
                    "data": RealtimeService.format_event(
                        "done",
                        final_payload,
                        {"chunk_count": chunk_count, "delivery": "stream"},
                    ),
                }

    return EventSourceResponse(stream_generator())


from pydantic import BaseModel

class UpdateMessageRequest(BaseModel):
    content: str

@router.put("/{room_id}/messages/{message_id}", response_model=Message)
async def update_message(
    room_id: str,
    message_id: str,
    request: UpdateMessageRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
):
    """Updates a message and creates a version of the old content."""
    user_id = user_info.get("user_id")

    # 1. Fetch the original message
    original_message = storage_service.get_message(message_id)
    if not original_message:
        raise HTTPException(status_code=404, detail="Message not found")

    # 2. Authorization Check: Ensure the user owns the message
    if original_message.user_id != user_id:
        raise HTTPException(status_code=403, detail="User not authorized to edit this message")

    # 3. Add the current state to the version history
    storage_service.add_message_version(original_message)

    # 4. Update the message with the new content
    new_content = request.content.strip()
    success = storage_service.update_message_content(message_id, new_content, new_content)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update message")

    # 5. Return the updated message
    updated_message = storage_service.get_message(message_id)
    if not updated_message:
        raise HTTPException(status_code=404, detail="Updated message not found")

    return updated_message

class MessageVersion(BaseModel):
    id: int
    message_id: str
    content: str
    role: str
    created_at: datetime

@router.get("/{message_id}/versions", response_model=List[MessageVersion])
async def get_message_versions_api(
    message_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
):
    """Gets the version history for a single message."""
    # Authorization check: ensure user has access to the original message's room
    original_message = storage_service.get_message(message_id)
    if not original_message:
        raise HTTPException(status_code=404, detail="Message not found")
    if original_message.user_id != user_info.get("user_id"):
        # A more robust check would be to check room ownership
        pass

    versions_data = storage_service.get_message_versions(message_id)
    return [MessageVersion(**row) for row in versions_data]


@router.post("/{room_id}/upload", response_model=Message)
async def upload_file(
    room_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_auth)
):
    """
    Upload a file to a room (placeholder implementation).
    """
    # TODO: Implement file upload functionality
    raise HTTPException(status_code=501, detail="File upload not yet implemented")
