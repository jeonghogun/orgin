"""
Review-related API endpoints
"""

import logging
import uuid
import uuid
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
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

@router.post("/rooms/{sub_room_id}/reviews", response_model=ReviewMeta)
async def create_review_and_start_process(
    sub_room_id: str,
    review_request: CreateReviewRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    review_service: ReviewService = Depends(get_review_service),
    redis_client: redis.Redis = Depends(get_redis_client),
    Idempotency_Key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Create a new review and immediately start the asynchronous review process.
    This endpoint supports an Idempotency-Key header to prevent duplicate requests.
    """
    if Idempotency_Key:
        cached_response = redis_client.get(f"idempotency:{Idempotency_Key}")
        if cached_response:
            logger.info(f"Idempotency key '{Idempotency_Key}' hit. Returning cached response.")
            return JSONResponse(content=json.loads(cached_response), status_code=200)

    # Verify sub-room exists and belongs to user
    sub_room = storage_service.get_room(sub_room_id)
    if not sub_room or sub_room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=404, detail="Sub-room not found or access denied.")
    if sub_room.type != "sub":
        raise HTTPException(status_code=400, detail="Reviews can only be created from sub-rooms.")

    try:
        # 1. Create the review room
        review_room_id = generate_id("review")
        review_room = Room(
            room_id=review_room_id,
            name=f"검토: {review_request.topic}",
            owner_id=user_info["user_id"],
            parent_id=sub_room_id,
            type="review",
            created_at=get_current_timestamp(),
            updated_at=get_current_timestamp(),
        )
        storage_service.save_room(review_room)
        logger.info(f"Created review room {review_room_id} for sub-room {sub_room_id}")

        # 2. Create the review metadata, linking it to the new room
        review_id = generate_id("review-meta")
        review_meta = ReviewMeta(
            review_id=review_id,
            room_id=review_room_id,  # Link to the new review room
            topic=review_request.topic,
            instruction=review_request.instruction,
            status="pending",
            total_rounds=3,
            created_at=get_current_timestamp(),
        )
        storage_service.save_review_meta(review_meta)
        logger.info(f"Created review metadata {review_id} for room {review_room_id}")

        # 3. Start the asynchronous review process
        trace_id = str(uuid.uuid4())
        logger.info(f"Starting review process for review {review_id} with trace_id: {trace_id}")
        await review_service.start_review_process(
            review_id=review_id,
            review_room_id=review_room_id, # Pass the new room ID
            topic=review_request.topic,
            instruction=review_request.instruction,
            panelists=review_request.panelists,
            trace_id=trace_id,
        )

        if Idempotency_Key:
            response_json = review_meta.model_dump_json()
            redis_client.set(f"idempotency:{Idempotency_Key}", response_json, ex=IDEMPOTENCY_KEY_TTL)
            logger.info(f"Cached response for idempotency key '{Idempotency_Key}'.")

        return review_meta
    except Exception as e:
        logger.error(f"Error creating review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create review")


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


@router.get("/reviews/{review_id}", response_model=ReviewMeta)
async def get_review(
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> ReviewMeta:
    """Get review information"""
    review = storage_service.get_review_meta(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.get("/reviews/{review_id}/events", response_model=List[ReviewEvent])
async def get_review_events(
    review_id: str,
    since: Optional[int] = None,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),  # pyright: ignore[reportCallInDefaultInitializer]
):
    """Get review progress events."""
    events_data = storage_service.get_review_events(review_id, since)
    return [ReviewEvent(**event) for event in events_data]


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
