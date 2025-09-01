"""
Room-related API endpoints
"""

import logging
from typing import Dict, List, Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, JSONResponse

from app.services.storage_service import storage_service
from app.utils.helpers import generate_id, create_success_response, get_current_timestamp
from pydantic import BaseModel
from app.api.dependencies import AUTH_DEPENDENCY
from app.models.enums import RoomType
from app.models.schemas import CreateRoomRequest, Room, ExportData, ExportableReview, Message


logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["rooms"])


def _format_export_as_markdown(export_data: ExportData) -> str:
    """Helper function to format export data as a Markdown string."""
    lines = []
    lines.append(f"# Export for Room: {export_data.room_name} ({export_data.room_id})")
    lines.append(f"Exported on: {get_current_timestamp()}")
    lines.append("\n---\n")

    lines.append("## Chat History")
    if not export_data.messages:
        lines.append("_No messages in this room._")
    else:
        for msg in export_data.messages:
            lines.append(f"**{msg.role} ({msg.timestamp}):**")
            lines.append(f"> {msg.content}")
            lines.append("")
    lines.append("\n---\n")

    lines.append("## Reviews")
    if not export_data.reviews:
        lines.append("_No reviews initiated in this room._")
    else:
        for i, review in enumerate(export_data.reviews, 1):
            lines.append(f"### Review {i}: {review.topic}")
            lines.append(f"- **Status:** {review.status}")
            lines.append(f"- **Created:** {review.created_at}")
            lines.append(f"- **Summary:** {review.final_summary}")
            lines.append("- **Next Steps / Recommendations:**")
            if not review.next_steps:
                lines.append("  - _None provided._")
            else:
                for step in review.next_steps:
                    lines.append(f"  - {step}")
            lines.append("")

    return "\n".join(lines)


@router.post("", response_model=Room)
async def create_room(
    room_request: CreateRoomRequest, user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Create a new chat room with hierarchy rules."""
    user_id = user_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user information")

    # Rule: One 'main' room per user
    if room_request.type == RoomType.MAIN:
        existing_rooms = await storage_service.get_rooms_by_owner(user_id)
        if any(r.type == RoomType.MAIN for r in existing_rooms):
            raise HTTPException(
                status_code=400, detail="Main room already exists for this user."
            )

    # Rule: 'sub' and 'review' rooms must have a valid parent
    if room_request.type in [RoomType.SUB, RoomType.REVIEW]:
        if not room_request.parent_id:
            raise HTTPException(
                status_code=400, detail="Sub/Review rooms must have a parent_id."
            )
        parent_room = await storage_service.get_room(room_request.parent_id)
        if not parent_room:
            raise HTTPException(
                status_code=404, detail=f"Parent room {room_request.parent_id} not found."
            )
        if room_request.type == RoomType.SUB and parent_room.type != RoomType.MAIN:
            raise HTTPException(
                status_code=400, detail="Sub rooms must have a main room as a parent."
            )
        if room_request.type == RoomType.REVIEW and parent_room.type != RoomType.SUB:
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


class UpdateRoomRequest(BaseModel):
    name: str


@router.patch("/{room_id}", response_model=Room)
async def update_room_name(
    room_id: str,
    room_request: UpdateRoomRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
):
    """Update the name of a room."""
    user_id = user_info.get("user_id")
    room = await storage_service.get_room(room_id)

    # Check ownership
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Perform the update
    success = await storage_service.update_room_name(room_id, room_request.name)
    if not success:
        # This might happen in a race condition where room is deleted after get_room
        raise HTTPException(status_code=404, detail="Room not found during update")

    # Return the updated room
    updated_room = await storage_service.get_room(room_id)
    return updated_room


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
    if room.type == RoomType.MAIN:
        raise HTTPException(status_code=400, detail="Main room cannot be deleted.")

    try:
        success = await storage_service.delete_room(room_id)
        if not success:
            raise HTTPException(status_code=404, detail="Room not found during deletion.")
    except Exception as e:
        logger.error(f"Error deleting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete room")


@router.get("/{room_id}/export")
async def export_room_data(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    format: Literal["json", "markdown"] = Query("json", description="The desired export format."),
):
    """Export room data, including chat history and all review summaries."""
    try:
        if not user_info or "user_id" not in user_info:
            raise HTTPException(status_code=400, detail="Invalid user information")

        room = await storage_service.get_room(room_id)
        if not room or room.owner_id != user_info.get("user_id"):
            raise HTTPException(status_code=404, detail="Room not found or access denied")

        messages = await storage_service.get_messages(room_id)
        full_reviews = await storage_service.get_full_reviews_by_room(room_id)

        exportable_reviews = []
        for review in full_reviews:
            next_steps = []
            summary = "Not completed."
            if review.final_report:
                summary = review.final_report.get("executive_summary", "Summary not available.")
                # Extract next steps from alternatives and recommendations
                next_steps.extend(review.final_report.get("alternatives", []))
                rec = review.final_report.get("recommendation")
                if rec:
                    next_steps.append(f"Final Recommendation: {rec}")

            exportable_reviews.append(
                ExportableReview(
                    topic=review.topic,
                    status=review.status,
                    created_at=review.created_at,
                    final_summary=summary,
                    next_steps=next_steps,
                )
            )

        export_data = ExportData(
            room_id=room_id,
            room_name=room.name,
            messages=messages,
            reviews=exportable_reviews,
            export_timestamp=get_current_timestamp(),
        )

        if format == "markdown":
            markdown_content = _format_export_as_markdown(export_data)
            return Response(
                content=markdown_content,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f"attachment; filename=export_room_{room_id}.md"
                },
            )

        # Default to JSON
        return JSONResponse(content=export_data.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting room {room_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed")
