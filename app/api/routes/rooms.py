"""
Room-related API endpoints - Refactored for synchronous operations and standardized errors.
"""

import logging
import asyncio
from typing import Dict, List, Literal
from fastapi import APIRouter, Query, Depends
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from app.services.cache_service import CacheService, get_cache_service

from app.core.errors import NotFoundError, InvalidRequestError, ForbiddenError
from app.services.storage_service import storage_service
from app.utils.helpers import generate_id, get_current_timestamp
from app.api.dependencies import AUTH_DEPENDENCY
from app.models.enums import RoomType
from app.models.schemas import CreateRoomRequest, Room, ExportData, ExportableReview


logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["rooms"])


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
def create_room(
    room_request: CreateRoomRequest, user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Create a new chat room with hierarchy rules."""
    user_id = user_info.get("user_id")
    if not user_id:
        raise InvalidRequestError("Invalid user information.")

    if room_request.type == RoomType.MAIN:
        existing_rooms = storage_service.get_rooms_by_owner(user_id)
        if any(r.type == RoomType.MAIN for r in existing_rooms):
            raise InvalidRequestError("Main room already exists for this user.")

    if room_request.type in [RoomType.SUB, RoomType.REVIEW]:
        if not room_request.parent_id:
            raise InvalidRequestError("Sub/Review rooms must have a parent_id.")
        parent_room = storage_service.get_room(room_request.parent_id)
        if not parent_room:
            raise NotFoundError("room", room_request.parent_id)
        if room_request.type == RoomType.SUB and parent_room.type != RoomType.MAIN:
            raise InvalidRequestError("Sub rooms must have a main room as a parent.")
        if room_request.type == RoomType.REVIEW and parent_room.type != RoomType.SUB:
            raise InvalidRequestError("Review rooms must have a sub room as a parent.")

    room_id = generate_id()
    new_room = storage_service.create_room(
        room_id=room_id,
        name=room_request.name,
        owner_id=user_id,
        room_type=room_request.type,
        parent_id=room_request.parent_id,
    )
    return new_room


@router.get("", response_model=List[Room])
async def get_rooms(
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    cache_service: CacheService = Depends(get_cache_service)
):
    """Get all rooms for a user, with caching."""
    user_id = user_info.get("user_id")
    if not user_id:
        raise InvalidRequestError("Invalid user information.")

    cache_key = f"rooms:{user_id}"

    # 1. Try to get from cache
    cached_rooms_data = await cache_service.get(cache_key)
    if cached_rooms_data:
        # Pydantic models need to be reconstructed from dict
        return [Room(**room_data) for room_data in cached_rooms_data]

    # 2. If miss, get from DB
    # Run the synchronous DB call in a separate thread to avoid blocking the event loop
    rooms = await asyncio.to_thread(storage_service.get_rooms_by_owner, user_id)

    # 3. Store in cache for next time
    if rooms:
        # We cache the list of dicts from the model dump
        await cache_service.set(cache_key, [room.model_dump() for room in rooms])

    return rooms


@router.get("/{room_id}", response_model=Room)
def get_room(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get room information"""
    room = storage_service.get_room(room_id)
    if not room:
        raise NotFoundError("room", room_id)
    if room.owner_id != user_info.get("user_id"):
        raise ForbiddenError()
    return room


class UpdateRoomRequest(BaseModel):
    name: str


@router.patch("/{room_id}", response_model=Room)
def update_room_name(
    room_id: str,
    room_request: UpdateRoomRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
):
    """Update the name of a room."""
    user_id = user_info.get("user_id")
    room = storage_service.get_room(room_id)

    if not room:
        raise NotFoundError("room", room_id)
    if room.owner_id != user_id:
        raise ForbiddenError()

    success = storage_service.update_room_name(room_id, room_request.name)
    if not success:
        raise NotFoundError("room", room_id)

    updated_room = storage_service.get_room(room_id)
    if not updated_room:
        # This is an edge case, but good to handle
        raise NotFoundError("room", room_id)
    return updated_room


@router.delete("/{room_id}", status_code=204)
def delete_room(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Delete a room."""
    user_id = user_info.get("user_id")
    room = storage_service.get_room(room_id)
    if not room:
        raise NotFoundError("room", room_id)
    if room.owner_id != user_id:
        raise ForbiddenError()

    if room.type == RoomType.MAIN:
        raise InvalidRequestError("Main room cannot be deleted.")

    success = storage_service.delete_room(room_id)
    if not success:
        raise NotFoundError("room", room_id)

    return Response(status_code=204)


@router.get("/{room_id}/export")
def export_room_data(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    format: Literal["json", "markdown"] = Query("json", description="The desired export format."),
):
    """Export room data, including chat history and all review summaries."""
    if not user_info or "user_id" not in user_info:
        raise InvalidRequestError("Invalid user information")

    room = storage_service.get_room(room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise NotFoundError("room", room_id)

    messages = storage_service.get_messages(room_id)
    full_reviews = storage_service.get_full_reviews_by_room(room_id)

    exportable_reviews = []
    for review in full_reviews:
        next_steps = []
        summary = "Not completed."
        if review.final_report:
            summary = review.final_report.get("executive_summary", "Summary not available.")
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
            headers={"Content-Disposition": f"attachment; filename=export_room_{room_id}.md"},
        )

    return JSONResponse(content=export_data.model_dump())
