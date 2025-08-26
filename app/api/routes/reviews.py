"""
Review-related API endpoints
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException

from app.services.storage_service import storage_service
from app.services.review_service import review_service
from app.utils.helpers import generate_id, get_current_timestamp, create_success_response
from app.models.schemas import CreateReviewRequest, ReviewMeta, ReviewEvent
from app.api.dependencies import AUTH_DEPENDENCY

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["reviews"])


@router.post("/rooms/{sub_room_id}/reviews", response_model=ReviewMeta)
async def create_review_and_start_process(
    sub_room_id: str,
    review_request: CreateReviewRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
):
    """
    Create a new review and immediately start the asynchronous review process.
    """
    # Verify sub-room exists and belongs to user
    sub_room = await storage_service.get_room(sub_room_id)
    if not sub_room or sub_room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=404, detail="Sub-room not found or access denied.")
    if sub_room.type != "sub":
        raise HTTPException(status_code=400, detail="Reviews can only be created from sub-rooms.")

    try:
        review_id = generate_id()
        review_meta = ReviewMeta(
            review_id=review_id,
            room_id=sub_room_id,
            topic=review_request.topic,
            instruction=review_request.instruction,
            status="pending",  # Status is pending until the first task runs
            total_rounds=3,
            current_round=0,
            created_at=get_current_timestamp(),
        )
        await storage_service.save_review_meta(review_meta)

        # Start the async review process
        review_service.start_review_process(
            review_id=review_id,
            topic=review_request.topic,
            instruction=review_request.instruction
        )

        return review_meta
    except Exception as e:
        logger.error(f"Error creating review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create review")


@router.get("/reviews/{review_id}", response_model=ReviewMeta)
async def get_review(review_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get review information"""
    review = await storage_service.get_review_meta(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review

@router.get("/reviews/{review_id}/events", response_model=List[ReviewEvent])
async def get_review_events(
    review_id: str,
    since: Optional[int] = None,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
):
    """Get review progress events."""
    events_data = await storage_service.get_review_events(review_id, since)
    return [ReviewEvent(**event) for event in events_data]

@router.get("/reviews/{review_id}/report")
async def get_review_report(
    review_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Get the final consolidated review report."""
    report = await storage_service.get_final_report(review_id)
    if not report:
        raise HTTPException(
            status_code=404, detail="Report not found. It may still be generating."
        )
    return create_success_response(data=report)
