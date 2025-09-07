"""
Search-related API endpoints
"""

import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.utils.helpers import create_success_response
from app.services.external_api_service import ExternalSearchService
from app.services.rag_service import get_rag_service
from app.services.conversation_service import get_conversation_service
from app.api.dependencies import AUTH_DEPENDENCY, get_search_service

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["search"])

# Request/Response models
class ConversationSearchRequest(BaseModel):
    query: str
    thread_id: Optional[str] = None
    limit: int = 10
    include_attachments: bool = True

class ConversationSearchResult(BaseModel):
    message_id: str
    thread_id: str
    content: str
    role: str
    created_at: int
    relevance_score: float
    source: str  # "message" or "attachment"


@router.get("")
async def search(
    q: str,
    n: int = 5,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    search_service: ExternalSearchService = Depends(get_search_service),  # pyright: ignore[reportCallInDefaultInitializer]
):
    """Search external sources"""
    try:
        results = await search_service.web_search(q, n)
        return create_success_response(data={"query": q, "results": results})
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")


@router.get("/wiki")
async def wiki_search(
    topic: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    search_service: ExternalSearchService = Depends(get_search_service),  # pyright: ignore[reportCallInDefaultInitializer]
):
    """Search Wikipedia"""
    try:
        summary = await search_service.wiki_summary(topic)
        return create_success_response(data={"topic": topic, "summary": summary})
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}")
        raise HTTPException(status_code=500, detail="Wikipedia search failed")


@router.post("/conversations")
async def search_conversations(
    request: ConversationSearchRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    rag_service = Depends(get_rag_service),
    convo_service = Depends(get_conversation_service),
):
    """Search conversations using hybrid RAG (BM25 + vector similarity)"""
    try:
        user_id = user_info.get("user_id")
        results = []
        
        # Search in messages
        message_results = await _search_messages(
            request.query, 
            request.thread_id, 
            user_id, 
            convo_service, 
            request.limit
        )
        results.extend(message_results)
        
        # Search in attachments if requested
        if request.include_attachments and request.thread_id:
            attachment_results = await _search_attachments(
                request.query, 
                request.thread_id, 
                rag_service, 
                request.limit
            )
            results.extend(attachment_results)
        
        # Sort by relevance score and limit results
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = results[:request.limit]
        
        return {
            "query": request.query,
            "total_results": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Conversation search error: {e}")
        raise HTTPException(status_code=500, detail="Conversation search failed")


async def _search_messages(
    query: str, 
    thread_id: Optional[str], 
    user_id: str, 
    convo_service, 
    limit: int
) -> List[Dict]:
    """Search in conversation messages using text search."""
    try:
        # Use PostgreSQL full-text search
        if thread_id:
            sql_query = """
                SELECT id, thread_id, content, role, created_at,
                       ts_rank(content_tsvector, plainto_tsquery('english', %s)) as rank
                FROM conversation_messages
                WHERE thread_id = %s 
                  AND content_tsvector @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
            """
            params = (query, thread_id, query, limit)
        else:
            # Search across all user's threads
            sql_query = """
                SELECT cm.id, cm.thread_id, cm.content, cm.role, cm.created_at,
                       ts_rank(cm.content_tsvector, plainto_tsquery('english', %s)) as rank
                FROM conversation_messages cm
                JOIN conversation_threads ct ON cm.thread_id = ct.thread_id
                WHERE ct.user_id = %s 
                  AND cm.content_tsvector @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
            """
            params = (query, user_id, query, limit)
        
        results = convo_service.db.execute_query(sql_query, params)
        
        return [
            {
                "message_id": row["id"],
                "thread_id": row["thread_id"],
                "content": row["content"],
                "role": row["role"],
                "created_at": row["created_at"],
                "relevance_score": float(row["rank"]),
                "source": "message"
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"Message search error: {e}")
        return []


async def _search_attachments(
    query: str, 
    thread_id: str, 
    rag_service, 
    limit: int
) -> List[Dict]:
    """Search in attachment chunks using hybrid RAG."""
    try:
        # Get hybrid search results
        chunks_data = rag_service._get_thread_chunks(thread_id)
        if not chunks_data:
            return []
        
        hybrid_results = await rag_service._hybrid_search(query, chunks_data, limit)
        
        return [
            {
                "message_id": f"attachment_{chunk['id']}",
                "thread_id": thread_id,
                "content": chunk["chunk_text"],
                "role": "attachment",
                "created_at": 0,  # Chunks don't have timestamps
                "relevance_score": 0.8,  # Placeholder score
                "source": "attachment"
            }
            for chunk in hybrid_results
        ]
    except Exception as e:
        logger.error(f"Attachment search error: {e}")
        return []
