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
from app.core.metrics import SSE_SESSIONS_ACTIVE

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
async def stream_message(message_id: str, request: Request, convo_service: ConversationService = Depends(get_conversation_service)):
    draft_message = convo_service.get_message_by_id(message_id)
    if not draft_message:
        raise HTTPException(status_code=404, detail="Message not found.")

    user_id = convo_service.redis_client.get(f"stream_user:{message_id}")
    user_id = user_id.decode('utf-8') if user_id else "anonymous"

    rag_service = get_rag_service()
    history = convo_service.get_messages_by_thread(draft_message["room_id"], limit=20)[::-1]
    user_query = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")

    rag_context = ""
    if user_query:
        rag_context = await rag_service.get_context_from_attachments(user_query, draft_message["room_id"])

    messages_for_llm = [{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ["user", "assistant"]]
    system_prompt = "You are a helpful assistant."
    if rag_context:
        system_prompt += f"\n\n{rag_context}"
    messages_for_llm.insert(0, {"role": "system", "content": system_prompt})

    adapter = get_llm_adapter(draft_message.get("model", "gpt-4o-mini"))

    async def event_generator():
        SSE_SESSIONS_ACTIVE.inc()
        try:
            # Send an initial ping to keep the connection alive
            yield {"event": "ping", "data": "staying alive"}
            content, meta, total_tokens = "", {}, 0

            async for sse_event in adapter.generate_stream(message_id=message_id, messages=messages_for_llm, model=draft_message.get("model", "gpt-4o-mini"), temperature=0.7, max_tokens=2048):
                if await request.is_disconnected(): break
                if sse_event.event == "delta": content += sse_event.data.content
                elif sse_event.event == "usage":
                    meta = sse_event.data.model_dump()
                    total_tokens = meta.get("total_tokens", 0)
                yield {"event": sse_event.event, "data": sse_event.data.model_dump_json()}
        finally:
            SSE_SESSIONS_ACTIVE.dec()
            convo_service.update_message(message_id, content, "complete", meta)
            if total_tokens > 0 and user_id != "anonymous":
                convo_service.increment_token_usage(user_id, total_tokens)
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

    diff = difflib.unified_diff(
        msg2['content'].splitlines(keepends=True),
        msg1['content'].splitlines(keepends=True),
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

@router.post("/search")
async def search_conversations(
    request: Dict[str, Any],
    user_info: Dict[str, Any] = AUTH_DEPENDENCY,
    rag_service = Depends(get_rag_service),
    convo_service: ConversationService = Depends(get_conversation_service)
):
    """
    Search conversations using hybrid RAG (BM25 + vector similarity).
    """
    try:
        query = request.get("query", "")
        thread_id = request.get("thread_id")
        limit = request.get("limit", 10)
        include_attachments = request.get("include_attachments", True)
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        user_id = user_info.get("user_id")
        results = []
        
        # Search in messages using PostgreSQL full-text search
        if thread_id:
            sql_query = """
                SELECT message_id, room_id, content_searchable, role, timestamp,
                       ts_rank(ts, plainto_tsquery('simple', %s)) as rank
                FROM messages
                WHERE room_id = %s
                  AND ts @@ plainto_tsquery('simple', %s)
                ORDER BY rank DESC
                LIMIT %s
            """
            params = (query, thread_id, query, limit)
        else:
            # Search across all user's messages
            sql_query = """
                SELECT m.message_id, m.room_id, m.content_searchable, m.role, m.timestamp,
                       ts_rank(m.ts, plainto_tsquery('simple', %s)) as rank
                FROM messages m
                WHERE m.user_id = %s
                  AND m.ts @@ plainto_tsquery('simple', %s)
                ORDER BY rank DESC
                LIMIT %s
            """
            params = (query, user_id, query, limit)
        
        message_results = convo_service.db.execute_query(sql_query, params)
        
        for row in message_results:
            results.append({
                "message_id": row["message_id"],
                "thread_id": row["room_id"],
                "content": row["content_searchable"],
                "role": row["role"],
                "created_at": row["timestamp"],
                "relevance_score": float(row["rank"]),
                "source": "message"
            })
        
        # Search in attachments if requested
        if include_attachments and thread_id:
            chunks_data = rag_service._get_thread_chunks(thread_id)
            if chunks_data:
                hybrid_results = await rag_service._hybrid_search(query, chunks_data, limit)
                
                for chunk in hybrid_results:
                    results.append({
                        "message_id": f"attachment_{chunk['id']}",
                        "thread_id": thread_id,
                        "content": chunk["chunk_text"],
                        "role": "attachment",
                        "created_at": 0,
                        "relevance_score": 0.8,
                        "source": "attachment"
                    })
        
        # Sort by relevance score and limit results
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = results[:limit]
        
        return {
            "query": query,
            "total_results": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Conversation search error: {e}")
        raise HTTPException(status_code=500, detail="Conversation search failed")
