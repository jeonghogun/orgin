"""
Memory and context-related API endpoints
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends

from app.services.memory_service import MemoryService
from app.utils.helpers import create_success_response, maybe_await
from app.api.dependencies import AUTH_DEPENDENCY, get_memory_service

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["memory"])


@router.get("/context/{room_id}")
async def get_context(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    memory_service: MemoryService = Depends(get_memory_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, Any]:
    """Get conversation context"""
    try:
        context = await maybe_await(
            memory_service.get_context(room_id, user_info["user_id"])
        )
        return create_success_response(data=context.model_dump() if context else None)
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        raise HTTPException(status_code=500, detail="Failed to get context")


@router.get("/profile")
async def get_user_profile(
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    memory_service: MemoryService = Depends(get_memory_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, Any]:
    """Get user profile"""
    try:
        profile = await maybe_await(
            memory_service.get_user_profile(user_info["user_id"])
        )
        return create_success_response(data=profile.model_dump() if profile else None)
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user profile")


# The set_memory and get_memory endpoints are deprecated and have been removed.
# They are replaced by the new V2 User Fact system.
