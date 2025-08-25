"""
RAG-related API endpoints
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request

from app.services.rag_service import rag_service
from app.utils.helpers import create_success_response

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["rag"])

# Dependency for authentication (will be imported from main)
auth_dependency: Any = None

def set_auth_dependency(auth_dep: Any) -> None:
    """Set authentication dependency from main app"""
    global auth_dependency
    auth_dependency = auth_dep

@router.post("/query")
async def rag_query(
    request: Request,
    user_info: Dict[str, str] = auth_dependency
) -> Dict[str, Any]:
    """RAG 기반 질의응답"""
    try:
        body = await request.json()
        room_id = body.get("room_id")
        query = body.get("query")
        
        if not all([room_id, query]):
            raise HTTPException(status_code=400, detail="room_id and query are required")
        
        # 의도 감지
        from app.services.intent_service import intent_service
        intent_result = await intent_service.classify_intent(query, "rag_query")
        intent = intent_result["intent"]
        entities = intent_result.get("entities", {})
        
        # RAG 응답 생성
        response = await rag_service.generate_rag_response(
            room_id, user_info["user_id"], query, intent, entities, "rag_query"
        )
        
        return create_success_response(data={
            "query": query,
            "intent": intent,
            "entities": entities,
            "response": response
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG query error: {e}")
        raise HTTPException(status_code=500, detail="RAG query failed")
