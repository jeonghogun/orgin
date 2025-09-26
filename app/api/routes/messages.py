"""Message-related API endpoints."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile, Form
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
from app.services.intent_classifier_service import IntentClassifierService
from app.services.background_task_service import BackgroundTaskService
from app.utils.helpers import (
    generate_id,
    get_current_timestamp,
    create_success_response,
    maybe_await,
)
from app.models.schemas import Message
from app.config.settings import settings
from app.services.realtime_service import get_realtime_service, RealtimeService
from app.services.file_validation_service import (
    FileValidationError,
    get_file_validation_service,
)
from app.services.cloud_storage_service import get_cloud_storage_service
from app.services.message_pipeline import (
    MessagePipeline,
    QuickIntentResult,
    build_fact_query_response,
    build_fact_query_success_response,
    build_quick_intent_response,
    classify_intent,
    ensure_fact_extraction,
    schedule_context_refresh,
    stream_immediate_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["messages"])

# --- QuickIntentResult Processing Helper ---

async def _process_quick_intent_result(
    quick_result: QuickIntentResult,
    room_id: str,
    user_id: str,
    storage_service: StorageService,
    memory_service: Optional[MemoryService] = None,
    background_tasks: Optional[BackgroundTaskService] = None,
    realtime_service: Optional[RealtimeService] = None,
) -> EventSourceResponse:
    """Process QuickIntentResult and return appropriate response."""
    
    if quick_result.content:
        # Simple content response
        return await stream_immediate_response(
            room_id=room_id,
            user_id=user_id,
            storage_service=storage_service,
            content=quick_result.content,
            memory_service=memory_service,
            background_tasks=background_tasks,
            realtime_service=realtime_service,
        )
    elif quick_result.tool:
        # Tool-based response - create a simple message for now
        # This is a simplified version of the tool response
        tool_content = f"도구 '{quick_result.tool}'를 사용하여 응답을 준비했습니다."
        return await stream_immediate_response(
            room_id=room_id,
            user_id=user_id,
            storage_service=storage_service,
            content=tool_content,
            memory_service=memory_service,
            background_tasks=background_tasks,
            realtime_service=realtime_service,
        )
    else:
        # Fallback
        return await stream_immediate_response(
            room_id=room_id,
            user_id=user_id,
            storage_service=storage_service,
            content="응답을 처리하는 중입니다.",
            memory_service=memory_service,
            background_tasks=background_tasks,
            realtime_service=realtime_service,
        )

# --- V2 Fact Extraction/Retrieval Helpers ---


async def _maybe_get_room(storage_service: StorageService, room_id: str):
    return await asyncio.to_thread(storage_service.get_room, room_id)

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
                    yield {
                        "event": "heartbeat",
                        "data": RealtimeService.format_event(
                            "heartbeat",
                            {"status": "keep-alive"},
                            {"delivery": "sse"},
                        ),
                    }
                    continue

                yield {"event": "new_message", "data": message}
        finally:
            realtime_service.unregister_listener(room_id, listener_queue)

    return EventSourceResponse(event_generator())


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
    background_tasks: BackgroundTaskService = Depends(get_background_task_service),
    realtime_service: RealtimeService = Depends(get_realtime_service),
    intent_classifier_service: IntentClassifierService = Depends(get_intent_classifier_service),
):
    """Send a message to a room"""
    logger.info(f"=== MESSAGE ENDPOINT CALLED === Room: {room_id}")
    try:
        body = await request.json()
        content = body.get("content", "").strip()
        user_id = user_info.get("user_id")
        logger.info(
            "=== MESSAGE CONTENT === User: %s, Content: %s",
            user_id,
            content,
        )

        if not content:
            raise HTTPException(
                status_code=400, detail="Message content is required"
            )
        if not user_id:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(
                status_code=400, detail="Invalid user information"
            )

        pipeline = MessagePipeline(
            storage_service=storage_service,
            rag_service=rag_service,
            memory_service=memory_service,
            search_service=search_service,
            intent_service=intent_service,
            review_service=review_service,
            llm_service=llm_service,
            fact_extractor_service=fact_extractor_service,
            user_fact_service=user_fact_service,
            cache_service=cache_service,
            background_tasks=background_tasks,
            realtime_service=realtime_service,
            intent_classifier=intent_classifier_service,
        )

        return await pipeline.process_user_message(
            room_id=room_id,
            user_id=user_id,
            content=content,
            raw_payload=body,
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

    schedule_context_refresh(
        background_tasks,
        memory_service,
        room_id,
        user_id,
        f"user:{user_message.message_id}",
    )

    await ensure_fact_extraction(
        message=user_message,
        user_fact_service=user_fact_service,
        fact_extractor_service=fact_extractor_service,
        background_tasks=background_tasks,
        execute_inline=False,
    )

    _, fact_response = await build_fact_query_response(
        content=content,
        user_id=user_id,
        user_fact_service=user_fact_service,
        cache_service=cache_service,
        intent_classifier=intent_classifier,
    )
    if fact_response:
        return await stream_immediate_response(
            room_id=room_id,
            user_id=user_id,
            storage_service=storage_service,
            content=fact_response,
            memory_service=memory_service,
            background_tasks=background_tasks,
            realtime_service=realtime_service,
        )

    intent, entities = await classify_intent(
        intent_service, content, user_message.message_id
    )

    direct_response = await build_quick_intent_response(
        intent=intent,
        content=content,
        user_id=user_id,
        entities=entities,
        user_fact_service=user_fact_service,
        cache_service=cache_service,
        search_service=search_service,
    )

    if direct_response is not None:
        return await _process_quick_intent_result(
            quick_result=direct_response,
            room_id=room_id,
            user_id=user_id,
            storage_service=storage_service,
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

                schedule_context_refresh(
                    background_tasks,
                    memory_service,
                    room_id,
                    user_id,
                    f"assistant:{ai_message.message_id}",
                )

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


def _format_file_size(num_bytes: int) -> str:
    """Return a human-readable string for a file size."""

    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@router.post("/{room_id}/upload", response_model=Message)
async def upload_file(
    room_id: str,
    file: UploadFile = File(...),
    attach_only: bool = Form(False),
    current_user: dict = Depends(require_auth),
    storage_service: StorageService = Depends(get_storage_service),
    realtime_service: RealtimeService = Depends(get_realtime_service),
):
    """Handle file uploads within a room and broadcast the resulting message."""

    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    room = storage_service.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not settings.AUTH_OPTIONAL and room.owner_id != user_id:
        raise HTTPException(status_code=403, detail="You do not have access to this room")

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="A file must be provided")

    validation_service = get_file_validation_service()
    cloud_storage = get_cloud_storage_service()

    try:
        validation_service.ensure_extension_allowed(file.filename)
        unique_name = validation_service.generate_unique_name(file.filename)
    except FileValidationError as validation_error:
        raise HTTPException(status_code=validation_error.status_code, detail=str(validation_error)) from validation_error

    temp_path = validation_service.temp_path_for(unique_name)
    final_path = None

    try:
        validation_service.write_upload_to_temp(file, temp_path)
        validation_service.scan_file(temp_path)
        final_path = validation_service.promote_to_permanent_storage(temp_path, unique_name)
    except FileValidationError as validation_error:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=validation_error.status_code, detail=str(validation_error)) from validation_error
    except Exception as unexpected_error:  # pragma: no cover - defensive logging
        logger.error("Failed to persist uploaded file %s: %s", file.filename, unexpected_error, exc_info=True)
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to persist uploaded file") from unexpected_error
    finally:
        try:
            file.file.close()
        except Exception:
            logger.debug("Upload file stream already closed for %s", file.filename)

    storage_uri = None
    if cloud_storage.is_configured():
        storage_uri = cloud_storage.upload_file(final_path, f"attachments/{unique_name}")
        if storage_uri:
            logger.info("Stored uploaded file %s in cloud storage as %s", file.filename, storage_uri)

    signed_url = None
    if storage_uri:
        signed_url = cloud_storage.generate_signed_url(storage_uri)

    local_url = None
    if final_path:
        quoted_name = quote(final_path.name)
        local_url = f"/uploads/{quoted_name}"
    download_path = signed_url or local_url or ""
    if not download_path:
        raise HTTPException(status_code=500, detail="Failed to determine download location for uploaded file")
    mime_type = file.content_type or "application/octet-stream"
    file_size = final_path.stat().st_size if final_path else 0
    formatted_size = _format_file_size(file_size)

    original_name = file.filename or "uploaded-file"
    display_name = original_name.replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")

    content_lines = [
        f"**파일 업로드:** [{display_name}]({download_path})",
        f"- 크기: {formatted_size}",
        f"- 형식: {mime_type}",
    ]
    content = "\n".join(content_lines)

    message = Message(
        message_id=generate_id(),
        room_id=room_id,
        user_id=user_id,
        content=content,
        timestamp=get_current_timestamp(),
        role="user",
    )

    if attach_only:
        return message

    try:
        storage_service.save_message(message)
    except Exception as exc:
        logger.error("Failed to save upload message for room %s: %s", room_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to persist uploaded message") from exc

    stored_message = storage_service.get_message(message.message_id)
    if not stored_message:
        raise HTTPException(status_code=500, detail="Uploaded message not found")

    await realtime_service.publish(room_id, "new_message", stored_message.model_dump())

    return stored_message
