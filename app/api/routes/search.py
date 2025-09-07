"""
Search-related API endpoints for external sources.
"""

import logging
from typing import Dict
from fastapi import APIRouter, HTTPException, Depends

from app.utils.helpers import create_success_response
from app.services.external_api_service import ExternalSearchService
from app.api.dependencies import AUTH_DEPENDENCY, get_search_service

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str,
    n: int = 5,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    search_service: ExternalSearchService = Depends(get_search_service),
):
    """Search external sources"""
    try:
        results = await search_service.web_search(q, n)
        return create_success_response(data={"query": q, "results": results})
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Search failed")


@router.get("/wiki")
async def wiki_search(
    topic: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    search_service: ExternalSearchService = Depends(get_search_service),
):
    """Search Wikipedia"""
    try:
        summary = await search_service.wiki_summary(topic)
        return create_success_response(data={"topic": topic, "summary": summary})
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Wikipedia search failed")
