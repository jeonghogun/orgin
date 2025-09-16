"""
RAG-related API endpoints
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends

from app.services.rag_service import RAGService
from app.services.intent_service import IntentService
from app.utils.helpers import create_success_response
from app.api.dependencies import (
    AUTH_DEPENDENCY,
    get_rag_service,
    get_intent_service,
    get_memory_service,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["rag"])


@router.post("/query")
async def rag_query(
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    rag_service: RAGService = Depends(get_rag_service),  # pyright: ignore[reportCallInDefaultInitializer]
    intent_service: IntentService = Depends(get_intent_service),  # pyright: ignore[reportCallInDefaultInitializer]
    memory_service = Depends(get_memory_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, Any]:
    """RAG 기반 질의응답"""
    try:
        body = await request.json()
        room_id = body.get("room_id")
        query = body.get("query")

        if not all([room_id, query]):
            raise HTTPException(
                status_code=400, detail="room_id and query are required"
            )

        # 의도 감지
        intent_result = await intent_service.classify_intent(query, "rag_query")
        intent = intent_result["intent"]
        entities = intent_result.get("entities", {})

        # RAG 응답 생성
        memory_context = await memory_service.get_context(room_id, user_info["user_id"])
        response = await rag_service.generate_rag_response(
            room_id, user_info["user_id"], query, memory_context, "rag_query"
        )

        return create_success_response(
            data={
                "query": query,
                "intent": intent,
                "entities": entities,
                "response": response,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG query error: {e}")
        raise HTTPException(status_code=500, detail="RAG query failed")
