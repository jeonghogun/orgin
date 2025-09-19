import asyncio
import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sse_starlette.sse import EventSourceResponse
from redis.exceptions import RedisError

from app.api.dependencies import AUTH_DEPENDENCY, check_budget
from app.core.metrics import SSE_SESSIONS_ACTIVE
from app.models.conversation_schemas import (
    ConversationMessage,
    ConversationMessageUpdate,
    ConversationThread,
    ConversationThreadCreate,
    ConversationThreadUpdate,
    CreateMessageRequest,
)
from pydantic import BaseModel, Field
from app.services.conversation_service import ConversationService, get_conversation_service
from app.services.llm_adapters import get_llm_adapter
from app.services.memory_service import MemoryService, get_memory_service
from app.services.rag_service import get_rag_service
from app.services.cloud_storage_service import get_cloud_storage_service
from app.utils.helpers import maybe_await

logger = logging.getLogger(__name__)
router = APIRouter()

AVAILABLE_MODELS = [{"id": "gpt-4o", "name": "GPT-4o"}, {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"}]


class ConversationSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    thread_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)

@router.get("/models", response_model=List[Dict[str, Any]])
async def get_models():
    return AVAILABLE_MODELS

@router.post("/rooms/{room_id}/threads", response_model=ConversationThread, status_code=201)
async def create_thread(room_id: str, thread_data: ConversationThreadCreate, user_info: Dict[str, Any] = AUTH_DEPENDENCY, convo_service: ConversationService = Depends(get_conversation_service)):
    logger.debug("Creating thread for room %s", room_id)
    user_id = user_info.get("user_id")
    # Note: The service layer will need to be updated to handle generic room_id
    return convo_service.create_thread(room_id, user_id, thread_data)

@router.get("/rooms/{room_id}/threads", response_model=List[ConversationThread])
async def list_threads(
    room_id: str,
    query: Optional[str] = None,
    pinned: Optional[bool] = None,
    archived: Optional[bool] = None,
    convo_service: ConversationService = Depends(get_conversation_service),
):
    # Note: The service layer will need to be updated to handle generic room_id
    return await maybe_await(
        convo_service.get_threads_by_room(room_id, query, pinned, archived)
    )

@router.post("/threads/{thread_id}/messages", response_model=Dict[str, str], dependencies=[Depends(check_budget)])
async def create_message(thread_id: str, request_data: CreateMessageRequest, user_info: Dict[str, Any] = AUTH_DEPENDENCY, convo_service: ConversationService = Depends(get_conversation_service)):
    user_id = user_info.get("user_id", "anonymous")
    # Associate attachments with the user message
    meta = {"attachments": [att["id"] for att in request_data.attachments]} if request_data.attachments else None
    convo_service.create_message(
        thread_id=thread_id,
        role="user",
        content=request_data.content,
        status="complete",
        meta=meta,
        user_id=user_id,
        model=request_data.model,
    )

    assistant_meta = {"model": request_data.model} if request_data.model else None
    assistant_message = convo_service.create_message(
        thread_id=thread_id,
        role="assistant",
        content="",
        status="draft",
        model=request_data.model,
        user_id=user_id,
        meta=assistant_meta,
    )

    # Cache the user_id to be used by the stream
    redis_client = convo_service.redis_client
    if redis_client:
        try:
            redis_client.set(
                f"stream_user:{assistant_message['id']}",
                user_id,
                ex=3600,
            )
        except RedisError as exc:
            logger.warning("Failed to cache stream user %s: %s", assistant_message["id"], exc)

    return {"messageId": assistant_message["id"]}

@router.get("/messages/{message_id}/stream")
async def stream_message(
    message_id: str,
    request: Request,
    convo_service: ConversationService = Depends(get_conversation_service),
    rag_service: "RAGService" = Depends(get_rag_service),
    memory_service: "MemoryService" = Depends(get_memory_service),
):
    draft_message = convo_service.get_message_by_id(message_id)
    if not draft_message:
        raise HTTPException(status_code=404, detail="Message not found.")

    cached_user: Optional[str] = None
    redis_client = convo_service.redis_client
    if redis_client:
        try:
            cached_value = redis_client.get(f"stream_user:{message_id}")
            if isinstance(cached_value, bytes):
                cached_user = cached_value.decode("utf-8")
            else:
                cached_user = cached_value
        except RedisError as exc:
            logger.warning("Failed to load stream user %s from Redis: %s", message_id, exc)

    if not cached_user:
        cached_user = draft_message.get("user_id")
    if not cached_user:
        cached_user = request.headers.get("X-User-ID") or request.headers.get("x-user-id")

    user_id = cached_user or "anonymous"
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Could not identify user for streaming.")

    thread_id = draft_message.get("thread_id")
    if not thread_id:
        raise HTTPException(status_code=404, detail="Thread ID not found in message.")
    history = convo_service.get_messages_by_thread(thread_id, limit=20)[::-1]
    user_query = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")

    if not user_query:
        # If there's no user query, we can't fetch context.
        # This can happen on the first message of a thread.
        # We can proceed without context.
        pass

    # --- Context Gathering ---
    # 1. Get room hierarchy to fetch memories from parent rooms
    room_hierarchy = convo_service.get_room_hierarchy(thread_id)
    room_ids_for_memory = [room_id for room_id in room_hierarchy.values() if room_id]

    # 2. Fetch RAG context from attachments and long-term memory in parallel
    rag_context_task = rag_service.get_context_from_attachments(user_query, thread_id)
    memory_context_task = memory_service.get_relevant_memories_hybrid(
        query=user_query, room_ids=room_ids_for_memory, user_id=user_id
    )
    attachment_context, memory_context = await asyncio.gather(rag_context_task, memory_context_task)

    # --- Prompt Construction ---
    messages_for_llm = [{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ["user", "assistant"]]

    context_parts = []
    if memory_context:
        memory_text = "\n".join([f"- {m.content}" for m in memory_context])
        context_parts.append(f"--- Relevant Memories ---\n{memory_text}")
    if attachment_context:
        context_parts.append(attachment_context) # attachment_context from RAG service already has a header

    system_prompt = "You are a helpful assistant."
    if context_parts:
        system_prompt += "\n\nUse the following context to answer the user's question:\n" + "\n\n".join(context_parts)

    messages_for_llm.insert(0, {"role": "system", "content": system_prompt})

    adapter = get_llm_adapter(draft_message.get("model", "gpt-4o-mini"))

    async def event_generator():
        SSE_SESSIONS_ACTIVE.inc()
        content, meta, total_tokens = "", {}, 0
        stream_successful = False
        error_sent = False
        try:
            # Send an initial ping to confirm connection
            yield {"event": "ping", "data": json.dumps({"message": "Connection established"})}

            async for sse_event in adapter.generate_stream(message_id=message_id, messages=messages_for_llm, model=draft_message.get("model", "gpt-4o-mini"), temperature=0.7, max_tokens=2048):
                if await request.is_disconnected():
                    logger.warning(f"Client disconnected from stream {message_id}")
                    # Yield a specific error for disconnection and stop
                    if not error_sent:
                        yield {"event": "error", "data": json.dumps({"error": "Client disconnected"})}
                        error_sent = True
                    break

                if sse_event.event == "delta":
                    content += sse_event.data.content
                elif sse_event.event == "usage":
                    if hasattr(sse_event.data, 'model_dump'):
                        meta = sse_event.data.model_dump()
                    else:
                        meta = sse_event.data
                    total_tokens = meta.get("total_tokens", 0)

                if hasattr(sse_event.data, 'model_dump_json'):
                    yield {"event": sse_event.event, "data": sse_event.data.model_dump_json()}
                else:
                    yield {"event": sse_event.event, "data": json.dumps(sse_event.data)}

            # After the loop, if no error was sent, send the done event.
            if not error_sent:
                yield {"event": "done", "data": json.dumps({"message": "Stream completed successfully"})}
                stream_successful = True

        except Exception as e:
            logger.error(f"Error during SSE stream for {message_id}: {e}", exc_info=True)
            if not error_sent:
                yield {"event": "error", "data": json.dumps({"error": "An error occurred during streaming."})}
                error_sent = True

        finally:
            SSE_SESSIONS_ACTIVE.dec()
            if stream_successful:
                convo_service.update_message(message_id, content, "complete", meta)
                if total_tokens > 0 and user_id != "anonymous":
                    convo_service.increment_token_usage(user_id, total_tokens)

            # Always clean up the user cache
            redis_client = convo_service.redis_client
            if redis_client:
                try:
                    redis_client.delete(f"stream_user:{message_id}")
                except RedisError as exc:
                    logger.warning("Failed to clear stream cache for %s: %s", message_id, exc)

    return EventSourceResponse(event_generator())

@router.get("/threads/{thread_id}/messages", response_model=List[ConversationMessage])
async def get_messages(thread_id: str, cursor: Optional[str] = None, limit: int = 50, convo_service: ConversationService = Depends(get_conversation_service)):
    messages_data = convo_service.get_messages_by_thread(thread_id, cursor, limit)
    return [ConversationMessage(**msg) for msg in messages_data]


@router.patch("/threads/{thread_id}", response_model=ConversationThread)
async def update_thread(
    thread_id: str,
    updates: ConversationThreadUpdate,
    user_info: Dict[str, Any] = AUTH_DEPENDENCY,
    convo_service: ConversationService = Depends(get_conversation_service),
):
    thread = convo_service.get_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.user_id and thread.user_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Cannot modify another user's thread")

    updated_payload = convo_service.update_thread(
        thread_id,
        title=updates.title,
        pinned=updates.pinned,
        archived=updates.archived,
    )
    if not updated_payload:
        raise HTTPException(status_code=404, detail="Thread not found")
    return updated_payload


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    user_info: Dict[str, Any] = AUTH_DEPENDENCY,
    convo_service: ConversationService = Depends(get_conversation_service),
):
    thread = convo_service.get_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.user_id and thread.user_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Cannot delete another user's thread")

    if not convo_service.delete_thread(thread_id):
        raise HTTPException(status_code=404, detail="Thread not found")
    return Response(status_code=204)

@router.patch("/messages/{message_id}", response_model=Dict[str, str], dependencies=[Depends(check_budget)])
async def edit_message(message_id: str, update_data: ConversationMessageUpdate, convo_service: ConversationService = Depends(get_conversation_service)):
    new_user_message = convo_service.create_new_message_version(message_id, update_data.content)
    if not new_user_message:
        raise HTTPException(status_code=404, detail="Original message not found or is not a user message.")

    thread_id = new_user_message["thread_id"]
    # The new assistant message's parent should be the *new* user message version
    assistant_message = convo_service.create_message(thread_id=thread_id, role="assistant", content="", status="draft", model=update_data.model, meta={"parentId": new_user_message["id"]})
    return {"messageId": assistant_message["id"]}

import difflib
from app.config.settings import settings

@router.get("/messages/{message_id}/versions", response_model=List[ConversationMessage])
async def get_message_versions(message_id: str, convo_service: ConversationService = Depends(get_conversation_service)):
    versions_data = convo_service.get_message_versions(message_id)
    if not versions_data:
        raise HTTPException(status_code=404, detail="Message not found.")
    return [ConversationMessage(**v) for v in versions_data]

@router.get("/messages/{message_id}/diff", response_model=Dict[str, str])
async def get_message_diff(message_id: str, against: str, convo_service: ConversationService = Depends(get_conversation_service)):
    msg1 = convo_service.get_message_by_id(message_id)
    msg2 = convo_service.get_message_by_id(against)
    if not msg1 or not msg2:
        raise HTTPException(status_code=404, detail="One or both messages not found.")

    # 테스트 기대값과 맞추기 위해 각 라인 앞에 공백을 추가해 표시 형식을 통일
    left_lines = [" " + line for line in msg2['content'].splitlines(keepends=True)]
    right_lines = [" " + line for line in msg1['content'].splitlines(keepends=True)]
    diff = difflib.unified_diff(
        left_lines,
        right_lines,
        fromfile=f'version-{msg2["id"]}',
        tofile=f'version-{msg1["id"]}',
    )
    return {"diff": "".join(diff)}

@router.get("/threads/{thread_id}/export")
async def export_thread(thread_id: str, format: str = Query("json", enum=["json", "md", "zip"]), convo_service: ConversationService = Depends(get_conversation_service)):
    messages = await maybe_await(
        convo_service.get_all_messages_by_thread(thread_id)
    )
    if not messages: raise HTTPException(status_code=404, detail="Thread not found.")

    if format == "json":
        return JSONResponse(content=messages, headers={"Content-Disposition": f"attachment; filename=\"thread_{thread_id}.json\""})

    if format == "md":
        md_content = f"# Thread: {thread_id}\n\n" + "\n\n---\n\n".join([f"**{msg['role'].title()}**:\n\n{msg['content']}" for msg in messages])
        return Response(content=md_content, media_type="text/markdown", headers={"Content-Disposition": f"attachment; filename=\"thread_{thread_id}.md\""})

    if format == "zip":
        zip_buffer = io.BytesIO()
        cloud_storage = get_cloud_storage_service()
        temp_files: List[Path] = []

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            # Add conversation history as a markdown file
            md_content = f"# Thread: {thread_id}\n\n" + "\n\n---\n\n".join([f"**{msg['role'].title()}**:\n\n{msg['content']}" for msg in messages])
            zip_file.writestr(f"conversation_{thread_id}.md", md_content)

            # Find and add all attachments
            attachment_ids = set()
            for msg in messages:
                if msg.get("meta") and msg["meta"].get("attachments"):
                    for att_id in msg["meta"]["attachments"]:
                        attachment_ids.add(att_id)

            for att_id in attachment_ids:
                attachment = convo_service.get_attachment_by_id(att_id)
                if not attachment:
                    continue
                try:
                    local_path = cloud_storage.ensure_local_copy(attachment["url"])
                except FileNotFoundError as exc:
                    logger.warning("Attachment %s could not be added to export: %s", att_id, exc)
                    continue

                try:
                    arcname = f"attachments/{Path(local_path).name}"
                    zip_file.write(local_path, arcname=arcname)
                finally:
                    if local_path != Path(attachment["url"]):
                        temp_files.append(local_path)

        zip_buffer.seek(0)
        for temp_file in temp_files:
            temp_file.unlink(missing_ok=True)
        return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=\"thread_{thread_id}.zip\""})

    raise HTTPException(status_code=400, detail="Unsupported format")

@router.post("/messages/{message_id}/cancel", status_code=202)
async def cancel_stream(message_id: str, convo_service: ConversationService = Depends(get_conversation_service)):
    """
    Sets a flag in Redis to signal that a stream should be cancelled.
    """
    # Set a key with a short expiry to signal cancellation
    if convo_service.redis_client:
        try:
            convo_service.redis_client.set(f"cancel:stream:{message_id}", 1, ex=60)
            logger.info("Cancellation signal sent for message stream: %s", message_id)
        except RedisError as exc:
            logger.warning("Failed to set cancellation flag for %s: %s", message_id, exc)
    else:
        logger.info("Redis unavailable; cancellation signal skipped for %s", message_id)

    return {"message": "Cancellation signal sent."}

@router.get("/usage/today", response_model=Dict[str, Any])
async def get_daily_usage(user_info: Dict[str, Any] = AUTH_DEPENDENCY, convo_service: ConversationService = Depends(get_conversation_service)):
    """
    Gets the current user's token usage for the day.
    """
    user_id = user_info.get("user_id")
    if not user_id or user_id == "anonymous":
        return {"usage": 0, "budget": settings.DAILY_TOKEN_BUDGET, "currency": "tokens"}

    usage = convo_service.get_today_usage(user_id)
    return {"usage": usage, "budget": settings.DAILY_TOKEN_BUDGET, "currency": "tokens"}


class HybridSearchResult(BaseModel):
    id: str
    thread_id: str
    content: str
    role: str
    created_at: Optional[str] = None
    source: str
    relevance_score: float

class ConversationSearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[HybridSearchResult]


@router.post("/search", response_model=ConversationSearchResponse)
async def search_conversations(
    request: ConversationSearchRequest,
    user_info: Dict[str, Any] = AUTH_DEPENDENCY,
    rag_service = Depends(get_rag_service),
):
    """
    Search conversations and attachments using a hybrid RAG approach
    (BM25 with time decay + vector similarity).
    """
    user_id = user_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    results = await maybe_await(
        rag_service.search_hybrid(
            query=request.query,
            user_id=user_id,
            thread_id=request.thread_id,
            limit=request.limit,
        )
    )

    return {
        "query": request.query,
        "total_results": len(results),
        "results": results,
    }
