"""
Memory and context-related API endpoints
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends

from app.services.memory_service import MemoryService
from app.utils.helpers import create_success_response
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
        context = await memory_service.get_context(room_id, user_info["user_id"])
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
        profile = await memory_service.get_user_profile(user_info["user_id"])
        return create_success_response(data=profile.model_dump() if profile else None)
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user profile")


@router.post("/memory")
async def set_memory(
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    memory_service: MemoryService = Depends(get_memory_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, Any]:
    """Set a memory entry"""
    try:
        body = await request.json()
        room_id = body.get("room_id")
        key = body.get("key")
        value = body.get("value")
        importance = body.get("importance", 1.0)
        ttl = body.get("ttl")

        if not all([room_id, key, value]):
            raise HTTPException(
                status_code=400, detail="room_id, key, and value are required"
            )

        success = await memory_service.set_memory(
            room_id, user_info["user_id"], key, value, importance, ttl
        )

        if success:
            return create_success_response(
                data={"success": True}, message="Memory set successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to set memory")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to set memory")


@router.get("/memory/{room_id}/{key}")
async def get_memory(
    room_id: str,
    key: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    memory_service: MemoryService = Depends(get_memory_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, Any]:
    """Get a memory entry"""
    try:
        value = await memory_service.get_memory(room_id, user_info["user_id"], key)
        return create_success_response(data={"value": value})
    except Exception as e:
        logger.error(f"Error getting memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to get memory")
