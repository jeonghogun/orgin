"""
Review-related API endpoints
"""

import logging
import uuid
import json
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from app.services.storage_service import StorageService
from app.services.review_service import ReviewService
from app.utils.helpers import generate_id, get_current_timestamp, create_success_response
from app.models.schemas import CreateReviewRequest, ReviewMeta, ReviewEvent, Room
from app.api.dependencies import (
    AUTH_DEPENDENCY,
    get_storage_service,
    get_review_service,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["reviews"])


import redis
from fastapi import Header

from app.api.dependencies import get_redis_client

IDEMPOTENCY_KEY_TTL = 60 * 60 * 24  # 24 hours



@router.get("/reviews", response_model=List[ReviewMeta])
async def get_reviews_by_room(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
) -> List[ReviewMeta]:
    """Get all reviews for a specific room"""
    # Verify room exists and belongs to user
    room = storage_service.get_room(room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=404, detail="Room not found or access denied.")
    
    reviews = storage_service.get_reviews_by_room(room_id)
    return reviews


@router.get("/reviews/{id}", response_model=ReviewMeta)
async def get_review(
    id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
) -> ReviewMeta:
    """
    Get review information by its review_id or the room_id of the review room.
    """
    # Try fetching by review_id first
    review = storage_service.get_review_meta(id)

    # If not found, try fetching by room_id
    if not review:
        review = storage_service.get_review_meta_by_room_id(id)

    # If still not found, or if found but owner doesn't match, raise error
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Verify that the associated room belongs to the user
    room = storage_service.get_room(review.room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied to review")

    return review


from sse_starlette.sse import EventSourceResponse
from app.services.redis_pubsub import redis_pubsub_manager

async def review_event_generator(review_id: str, request: Request):
    """
    Yields server-sent events for a specific review's progress.
    Listens to a Redis Pub/Sub channel.
    """
    # First, send all historical events for this review
    storage = get_storage_service()
    historical_events = storage.get_review_events(review_id)
    for event in historical_events:
        yield dict(event="historical_event", data=json.dumps(event))

    # Now, listen for live events from Redis Pub/Sub
    async with redis_pubsub_manager.subscribe(f"review_{review_id}") as subscriber:
        async for message in subscriber:
            if await request.is_disconnected():
                break
            # Messages from redis_pubsub_manager are already JSON strings
            yield dict(event="live_event", data=message)

@router.get("/reviews/{review_id}/events")
async def get_review_events_stream(
    request: Request,
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
):
    """
    Returns a Server-Sent Events (SSE) stream of review progress.
    """
    # First, verify the user has access to this review.
    review = storage_service.get_review_meta(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    room = storage_service.get_room(review.room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied to review")

    return EventSourceResponse(review_event_generator(review_id, request))


@router.get("/reviews/{review_id}/report", response_class=JSONResponse)
async def get_review_report(
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, Any]:
    """Get the final consolidated review report."""
    report = storage_service.get_final_report(review_id)
    if not report:
        raise HTTPException(
            status_code=404, detail="Report not found. It may still be generating."
        )
    # The helper returns a Dict, which FastAPI automatically converts to a JSONResponse
    return create_success_response(data=report)
