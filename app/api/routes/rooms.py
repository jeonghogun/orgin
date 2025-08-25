"""
Room-related API endpoints
"""
import logging
from typing import Dict
from fastapi import APIRouter, HTTPException, Request, Depends

from app.services.storage_service import storage_service
from app.utils.helpers import generate_id, create_success_response

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["rooms"])

# Authentication dependency function
async def require_auth(request: Request) -> Dict[str, str]:
    """Require authentication for protected endpoints"""
    from app.config.settings import settings
    
    if settings.AUTH_OPTIONAL:
        return {"user_id": "anonymous"}
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # In a real app, validate the token here
    token = auth_header.split(" ")[1]
    return {"user_id": "authenticated_user", "token": token}

@router.post("")
async def create_room(request: Request, user_info: Dict[str, str] = Depends(require_auth)):
    """Create a new chat room"""
    try:
        # Validate user_info
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")
        
        room_id = generate_id()
        room_name = f"Room {room_id[:8]}"
        
        room = await storage_service.create_room(room_id, room_name)
        
        return create_success_response(
            data={"room_id": room_id, "name": room_name},
            message="Room created successfully"
        )
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        raise HTTPException(status_code=500, detail="Failed to create room")

@router.get("/{room_id}")
async def get_room(room_id: str, user_info: Dict[str, str] = Depends(require_auth)):
    """Get room information"""
    try:
        # Validate user_info
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")
        
        room = await storage_service.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        return create_success_response(data=room.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get room")

@router.get("/{room_id}/export")
async def export_room_data(
    room_id: str,
    user_info: Dict[str, str] = Depends(require_auth)
):
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
            format="markdown"
        )
        
        return create_success_response(data=export_data.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Export failed")
