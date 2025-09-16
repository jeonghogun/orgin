"""
Room-related API endpoints - Refactored for synchronous operations and standardized errors.
"""

import logging
import asyncio
from typing import Dict, List, Literal, Optional
from fastapi import APIRouter, Query, Depends
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from app.services.cache_service import CacheService, get_cache_service

from app.core.errors import NotFoundError, InvalidRequestError, ForbiddenError, AppError
from app.services.storage_service import storage_service
from app.services.conversation_service import get_conversation_service
from app.services.llm_service import get_llm_service
from app.services.memory_service import get_memory_service
from app.utils.helpers import generate_id, get_current_timestamp
from app.api.dependencies import AUTH_DEPENDENCY
from app.models.enums import RoomType
from app.models.schemas import CreateRoomRequest, Room, ExportData, ExportableReview, Message


logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["rooms"])


async def _handle_sub_room_creation_context(
    parent_room_id: str, new_room_name: str, new_room_id: str, user_id: str
):
    """Helper to add context to a new sub-room based on parent history."""
    conversation_service = get_conversation_service()
    llm_service = get_llm_service()
    memory_service = get_memory_service()

    # 1. Get conversation history from parent room
    threads = await asyncio.to_thread(conversation_service.get_threads_by_room, parent_room_id)
    full_conversation = ""
    for thread in threads:
        messages = await asyncio.to_thread(conversation_service.get_all_messages_by_thread, thread.id)
        for msg in messages:
            full_conversation += f"{msg['role']}: {msg['content']}\n"

    # 2. Check if the new room's topic exists in the conversation
    initial_message_content = ""
    if new_room_name.lower() in full_conversation.lower():
        # Topic exists, summarize it
        system_prompt = f"You are a helpful assistant. Summarize the following conversation, focusing on the key points, facts, and decisions related to the topic: '{new_room_name}'. Provide a concise summary."
        user_prompt = full_conversation
        summary, _ = await llm_service.invoke("openai", "gpt-4o", system_prompt, user_prompt, "summary-gen")
        initial_message_content = f"이 세부룸은 메인룸의 '{new_room_name}' 논의를 기반으로 생성되었습니다.\n\n**핵심 요약:**\n{summary}"
    else:
        # Topic is new, inherit general context and profile
        profile = await memory_service.get_user_profile(user_id)
        context = await memory_service.get_context(parent_room_id, user_id)

        system_prompt = "You are a helpful AI assistant starting a new conversation. Based on the user's profile and the general context of the main room, generate a welcoming message to kick off the discussion about a new topic."
        user_prompt = f"New Topic: '{new_room_name}'\nUser Profile: {profile.model_dump_json() if profile else 'Not available'}\nMain Room Context: {context.model_dump_json() if context else 'Not available'}"

        welcome_message, _ = await llm_service.invoke("openai", "gpt-4o", system_prompt, user_prompt, "welcome-gen")
        initial_message_content = welcome_message

    # 3. Add the initial message to the new room
    if initial_message_content:
        initial_message = Message(
            message_id=generate_id("msg"),
            room_id=new_room_id,
            user_id="system",
            role="assistant",
            content=initial_message_content,
            timestamp=get_current_timestamp(),
        )
        await asyncio.to_thread(storage_service.save_message, initial_message)


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
    room_request: CreateRoomRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    cache_service: CacheService = Depends(get_cache_service),
):
    """Create a new chat room with hierarchy rules."""
    user_id = user_info.get("user_id")
    if not user_id:
        raise InvalidRequestError("Invalid user information.")

    if room_request.type == RoomType.MAIN:
        existing_rooms = await asyncio.to_thread(storage_service.get_rooms_by_owner, user_id)
        if any(r.type == RoomType.MAIN for r in existing_rooms):
            raise InvalidRequestError("Main room already exists for this user.")

    if room_request.type in [RoomType.SUB, RoomType.REVIEW]:
        if not room_request.parent_id:
            raise InvalidRequestError("Sub/Review rooms must have a parent_id.")
        parent_room = await asyncio.to_thread(storage_service.get_room, room_request.parent_id)
        if not parent_room:
            raise NotFoundError("room", room_request.parent_id)
        if room_request.type == RoomType.SUB and parent_room.type != RoomType.MAIN:
            raise InvalidRequestError("Sub rooms must have a main room as a parent.")
        if room_request.type == RoomType.REVIEW and parent_room.type != RoomType.SUB:
            raise InvalidRequestError("Review rooms must have a sub room as a parent.")

    room_id = generate_id()
    new_room = await asyncio.to_thread(
        storage_service.create_room,
        room_id=room_id,
        name=room_request.name,
        owner_id=user_id,
        room_type=room_request.type,
        parent_id=room_request.parent_id,
    )

    # If a sub-room is created, handle context inheritance
    if new_room.type == RoomType.SUB and new_room.parent_id:
        await _handle_sub_room_creation_context(
            parent_room_id=new_room.parent_id,
            new_room_name=new_room.name,
            new_room_id=new_room.room_id,
            user_id=user_id,
        )

    # Invalidate cache
    await cache_service.delete(f"rooms:{user_id}")

    return new_room


@router.get("", response_model=List[Room])
async def get_rooms(
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    Get all rooms for a user. If no rooms exist, create a default Main Room.
    Implements caching.
    """
    user_id = user_info.get("user_id")
    if not user_id:
        raise InvalidRequestError("Invalid user information.")

    cache_key = f"rooms:{user_id}"

    # 1. Try to get from cache
    cached_rooms_data = await cache_service.get(cache_key)
    if cached_rooms_data:
        return [Room(**room_data) for room_data in cached_rooms_data]

    # 2. If miss, get from DB
    rooms = await asyncio.to_thread(storage_service.get_rooms_by_owner, user_id)

    # 3. If no rooms exist for the user, create a default Main Room
    if not rooms:
        new_room_id = generate_id()
        # Run synchronous DB call in a separate thread
        main_room = await asyncio.to_thread(
            storage_service.create_room,
            room_id=new_room_id,
            name="Main Room",
            owner_id=user_id,
            room_type=RoomType.MAIN,
            parent_id=None
        )
        rooms = [main_room]
        # The cache was missed, so we don't need to invalidate, just set it below.

    # 4. Store in cache for next time
    if rooms:
        await cache_service.set(cache_key, [room.model_dump() for room in rooms])

    return rooms


@router.get("/{room_id}", response_model=Room)
def get_room(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get room information"""
    try:
        room = storage_service.get_room(room_id)
        if not room:
            raise NotFoundError("room", room_id)
        if room.owner_id != user_info.get("user_id"):
            raise ForbiddenError()
        return room
    except Exception as e:
        if "Simulated DB is down" in str(e):
            raise AppError("INTERNAL_ERROR", "Failed to retrieve room")
        raise


class UpdateRoomRequest(BaseModel):
    name: str


@router.patch("/{room_id}", response_model=Room)
async def update_room_name(
    room_id: str,
    room_request: UpdateRoomRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    cache_service: CacheService = Depends(get_cache_service),
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

    # Invalidate cache
    await cache_service.delete(f"rooms:{user_id}")

    updated_room = storage_service.get_room(room_id)
    if not updated_room:
        # This is an edge case, but good to handle
        raise NotFoundError("room", room_id)
    return updated_room


@router.delete("/{room_id}", status_code=204)
async def delete_room(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    cache_service: CacheService = Depends(get_cache_service),
):
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

    # Invalidate cache
    await cache_service.delete(f"rooms:{user_id}")

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


class CreateReviewRoomInteractiveRequest(BaseModel):
    topic: str
    history: Optional[List[Dict[str, str]]] = None

class PromoteMemoryRequest(BaseModel):
    sub_room_id: str
    criteria_text: str = "General summary of key findings."

class CreateReviewRoomInteractiveResponse(BaseModel):
    status: Literal["created", "needs_more_context"]
    question: Optional[str] = None
    room: Optional[Room] = None


@router.post("/{room_id}/promote-memory", response_model=Dict[str, str])
async def promote_memory_from_sub_room(
    room_id: str, # This is the main_room_id
    request: PromoteMemoryRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
):
    """
    Promotes memories from a sub-room to its parent main room.
    """
    user_id = user_info.get("user_id")
    memory_service = get_memory_service()

    # Basic validation
    main_room = await asyncio.to_thread(storage_service.get_room, room_id)
    if not main_room or main_room.owner_id != user_id or main_room.type != RoomType.MAIN:
        raise NotFoundError("main room", room_id)

    sub_room = await asyncio.to_thread(storage_service.get_room, request.sub_room_id)
    if not sub_room or sub_room.owner_id != user_id or sub_room.parent_id != room_id:
        raise InvalidRequestError("Invalid sub_room_id or it does not belong to the specified main room.")

    try:
        summary = await memory_service.promote_memories(
            sub_room_id=request.sub_room_id,
            main_room_id=room_id,
            user_id=user_id,
            criteria_text=request.criteria_text,
        )
        return {"status": "success", "summary": summary}
    except Exception as e:
        logger.error(f"Memory promotion failed for user {user_id}, main_room {room_id}, sub_room {request.sub_room_id}: {e}", exc_info=True)
        # In a real app, you'd want a more specific error, but this is a start
        raise AppError("INTERNAL_ERROR", "Failed to promote memories.")


from app.services.review_service import get_review_service, ReviewService

@router.post("/{parent_id}/create-review-room", response_model=CreateReviewRoomInteractiveResponse)
async def create_review_room_interactive(
    parent_id: str,
    request: CreateReviewRoomInteractiveRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    review_service: ReviewService = Depends(get_review_service),
):
    """
    Interactively creates a review room by calling the review service.
    This endpoint is now a thin wrapper around the service layer.
    """
    user_id = user_info.get("user_id")
    if not user_id:
        raise InvalidRequestError("Invalid user information.")

    return await review_service.create_interactive_review(
        parent_id=parent_id,
        topic=request.topic,
        user_id=user_id,
        history=request.history,
    )
