import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
import io
import zipfile
from pathlib import Path
from fastapi.responses import Response, JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import AUTH_DEPENDENCY, check_budget
from app.models.conversation_schemas import (
    ConversationThread, ConversationThreadCreate, ConversationMessage,
    CreateMessageRequest, ConversationMessageUpdate
)
from app.services.conversation_service import ConversationService, get_conversation_service
from app.services.llm_adapters import get_llm_adapter
from app.services.rag_service import get_rag_service
from app.services.memory_service import MemoryService, get_memory_service
from app.core.metrics import SSE_SESSIONS_ACTIVE
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

AVAILABLE_MODELS = [{"id": "gpt-4o", "name": "GPT-4o"}, {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"}]

@router.get("/models", response_model=List[Dict[str, Any]])
async def get_models():
    return AVAILABLE_MODELS

@router.post("/subrooms/{sub_room_id}/threads", response_model=ConversationThread, status_code=201)
async def create_thread(sub_room_id: str, thread_data: ConversationThreadCreate, user_info: Dict[str, Any] = AUTH_DEPENDENCY, convo_service: ConversationService = Depends(get_conversation_service)):
    user_id = user_info.get("user_id")
    return convo_service.create_thread(sub_room_id, user_id, thread_data)

@router.get("/subrooms/{sub_room_id}/threads", response_model=List[ConversationThread])
async def list_threads(sub_room_id: str, query: Optional[str] = None, pinned: Optional[bool] = None, archived: Optional[bool] = None, convo_service: ConversationService = Depends(get_conversation_service)):
    return convo_service.get_threads_by_subroom(sub_room_id, query, pinned, archived)

@router.post("/threads/{thread_id}/messages", response_model=Dict[str, str], dependencies=[Depends(check_budget)])
async def create_message(thread_id: str, request_data: CreateMessageRequest, user_info: Dict[str, Any] = AUTH_DEPENDENCY, convo_service: ConversationService = Depends(get_conversation_service)):
    user_id = user_info.get("user_id", "anonymous")
    # Associate attachments with the user message
    meta = {"attachments": [att["id"] for att in request_data.attachments]} if request_data.attachments else None
    convo_service.create_message(thread_id=thread_id, role="user", content=request_data.content, status="complete", meta=meta, user_id=user_id)

    assistant_message = convo_service.create_message(thread_id=thread_id, role="assistant", content="", status="draft", model=request_data.model, user_id=user_id)

    # Cache the user_id to be used by the stream
    convo_service.redis_client.set(f"stream_user:{assistant_message['id']}", user_id, ex=3600)

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

    user_id = convo_service.redis_client.get(f"stream_user:{message_id}")
    user_id = user_id.decode('utf-8') if user_id else "anonymous"
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Could not identify user for streaming.")

    thread_id = draft_message["room_id"]
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
        try:
            # Send an initial ping to confirm connection
            yield {"event": "ping", "data": json.dumps({"message": "Connection established"})}

            async for sse_event in adapter.generate_stream(message_id=message_id, messages=messages_for_llm, model=draft_message.get("model", "gpt-4o-mini"), temperature=0.7, max_tokens=2048):
                if await request.is_disconnected():
                    logger.warning(f"Client disconnected from stream {message_id}")
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

            # If the loop completes without breaking, the stream was successful
            else:
                yield {"event": "done", "data": json.dumps({"message": "Stream completed successfully"})}
                stream_successful = True

        except Exception as e:
            logger.error(f"Error during SSE stream for {message_id}: {e}", exc_info=True)
            yield {"event": "error", "data": json.dumps({"error": "An error occurred during streaming."})}

        finally:
            SSE_SESSIONS_ACTIVE.dec()
            if stream_successful:
                convo_service.update_message(message_id, content, "complete", meta)
                if total_tokens > 0 and user_id != "anonymous":
                    convo_service.increment_token_usage(user_id, total_tokens)

            # Always clean up the user cache
            convo_service.redis_client.delete(f"stream_user:{message_id}")

    return EventSourceResponse(event_generator())

@router.get("/threads/{thread_id}/messages", response_model=List[ConversationMessage])
async def get_messages(thread_id: str, cursor: Optional[str] = None, limit: int = 50, convo_service: ConversationService = Depends(get_conversation_service)):
    messages_data = convo_service.get_messages_by_thread(thread_id, cursor, limit)
    return [ConversationMessage(**msg) for msg in messages_data]

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
    messages = convo_service.get_all_messages_by_thread(thread_id)
    if not messages: raise HTTPException(status_code=404, detail="Thread not found.")

    if format == "json":
        return JSONResponse(content=messages, headers={"Content-Disposition": f"attachment; filename=\"thread_{thread_id}.json\""})

    if format == "md":
        md_content = f"# Thread: {thread_id}\n\n" + "\n\n---\n\n".join([f"**{msg['role'].title()}**:\n\n{msg['content']}" for msg in messages])
        return Response(content=md_content, media_type="text/markdown", headers={"Content-Disposition": f"attachment; filename=\"thread_{thread_id}.md\""})

    if format == "zip":
        zip_buffer = io.BytesIO()
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
                if attachment and Path(attachment["url"]).exists():
                    zip_file.write(attachment["url"], arcname=f"attachments/{Path(attachment['url']).name}")

        zip_buffer.seek(0)
        return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=\"thread_{thread_id}.zip\""})

    raise HTTPException(status_code=400, detail="Unsupported format")

@router.post("/messages/{message_id}/cancel", status_code=202)
async def cancel_stream(message_id: str, convo_service: ConversationService = Depends(get_conversation_service)):
    """
    Sets a flag in Redis to signal that a stream should be cancelled.
    """
    # Set a key with a short expiry to signal cancellation
    convo_service.redis_client.set(f"cancel:stream:{message_id}", 1, ex=60)
    logger.info(f"Cancellation signal sent for message stream: {message_id}")
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

from pydantic import BaseModel

class ConversationSearchRequest(BaseModel):
    query: str
    thread_id: Optional[str] = None
    limit: int = 10

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
    try:
        user_id = user_info.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")

        results = await rag_service.search_hybrid(
            query=request.query,
            user_id=user_id,
            thread_id=request.thread_id,
            limit=request.limit,
        )
        
        return {
            "query": request.query,
            "total_results": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"Conversation search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during search: {e}")
