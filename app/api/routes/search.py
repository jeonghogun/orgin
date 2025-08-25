"""
Search-related API endpoints
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request

from app.utils.helpers import create_success_response

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["search"])

# Dependency for authentication (will be imported from main)
auth_dependency: Any = None
external_search_service: Any = None

def set_dependencies(auth_dep: Any, search_service: Any) -> None:
    """Set dependencies from main app"""
    global auth_dependency, external_search_service
    auth_dependency = auth_dep
    external_search_service = search_service

@router.get("")
async def search(
    request: Request,
    q: str,
    n: int = 5,
    user_info: Dict[str, str] = auth_dependency
):
    """Search external sources"""
    try:
        results = await external_search_service.web_search(q, n)
        return create_success_response(data={
            "query": q,
            "results": results
        })
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")

@router.get("/wiki")
async def wiki_search(
    request: Request,
    topic: str,
    user_info: Dict[str, str] = auth_dependency
):
    """Search Wikipedia"""
    try:
        summary = await external_search_service.wiki_summary(topic)
        return create_success_response(data={
            "topic": topic,
            "summary": summary
        })
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}")
        raise HTTPException(status_code=500, detail="Wikipedia search failed")
