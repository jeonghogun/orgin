"""
Room-related API endpoints
"""

import logging
from typing import Dict, List
from fastapi import APIRouter, HTTPException

from app.services.storage_service import storage_service
from app.utils.helpers import generate_id, create_success_response
from app.api.dependencies import AUTH_DEPENDENCY
from app.models.schemas import CreateRoomRequest, Room

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["rooms"])


@router.post("", response_model=Room)
async def create_room(
    room_request: CreateRoomRequest, user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Create a new chat room with hierarchy rules."""
    user_id = user_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user information")

    # Rule: One 'main' room per user
    if room_request.type == "main":
        existing_rooms = await storage_service.get_rooms_by_owner(user_id)
        if any(r.type == "main" for r in existing_rooms):
            raise HTTPException(
                status_code=400, detail="Main room already exists for this user."
            )

    # Rule: 'sub' and 'review' rooms must have a valid parent
    if room_request.type in ["sub", "review"]:
        if not room_request.parent_id:
            raise HTTPException(
                status_code=400, detail="Sub/Review rooms must have a parent_id."
            )
        parent_room = await storage_service.get_room(room_request.parent_id)
        if not parent_room:
            raise HTTPException(
                status_code=404, detail=f"Parent room {room_request.parent_id} not found."
            )
        if room_request.type == "sub" and parent_room.type != "main":
            raise HTTPException(
                status_code=400, detail="Sub rooms must have a main room as a parent."
            )
        if room_request.type == "review" and parent_room.type != "sub":
            raise HTTPException(
                status_code=400, detail="Review rooms must have a sub room as a parent."
            )

    try:
        room_id = generate_id()
        new_room = await storage_service.create_room(
            room_id=room_id,
            name=room_request.name,
            owner_id=user_id,
            room_type=room_request.type,
            parent_id=room_request.parent_id,
        )
        return new_room
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        raise HTTPException(status_code=500, detail="Failed to create room")


@router.get("", response_model=List[Room])
async def get_rooms(user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get all rooms for a user."""
    user_id = user_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user information")

    try:
        rooms = await storage_service.get_rooms_by_owner(user_id)
        return rooms
    except Exception as e:
        logger.error(f"Error getting rooms for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get rooms")


@router.get("/{room_id}", response_model=Room)
async def get_room(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get room information"""
    try:
        room = await storage_service.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        # Basic ownership check
        if room.owner_id != user_info.get("user_id"):
            raise HTTPException(status_code=403, detail="Access denied")
        return room
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve room")


@router.delete("/{room_id}", status_code=204)
async def delete_room(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Delete a room."""
    user_id = user_info.get("user_id")
    room = await storage_service.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Main rooms cannot be deleted
    if room.type == "main":
        raise HTTPException(status_code=400, detail="Main room cannot be deleted.")

    try:
        success = await storage_service.delete_room(room_id)
        if not success:
            raise HTTPException(status_code=404, detail="Room not found during deletion.")
    except Exception as e:
        logger.error(f"Error deleting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete room")


@router.get("/{room_id}/export")
async def export_room_data(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Export room data"""
    try:
        # Validate user_info
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")

        # Get room data
        room = await storage_service.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        # Get messages
        messages = await storage_service.get_messages(room_id)

        # Create export data
        from app.models.schemas import ExportData
        from app.utils.helpers import get_current_timestamp

        export_data = ExportData(
            room_id=room_id,
            messages=messages,
            reviews=[],  # TODO: Implement get_reviews method
            export_timestamp=get_current_timestamp(),
            format="markdown",
        )

        return create_success_response(data=export_data.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Export failed")
