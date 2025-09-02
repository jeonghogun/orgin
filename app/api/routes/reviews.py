"""
Review-related API endpoints
"""
import asyncio
import logging
import uuid
import json
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.services.storage_service import StorageService
from app.services.review_service import ReviewService
from app.services.cache_service import CacheService
from app.utils.helpers import generate_id, get_current_timestamp, create_success_response
from app.models.schemas import CreateReviewRequest, ReviewMeta, ReviewEvent, Room
from app.core.errors import InvalidRequestError, NotFoundError
from app.api.dependencies import (
    AUTH_DEPENDENCY,
    get_storage_service,
    get_review_service,
    get_cache_service,
    get_redis_client,
)
import redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reviews"])

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
    if Idempotency_Key:
        cached_response = await asyncio.to_thread(redis_client.get, f"idempotency:{Idempotency_Key}")
        if cached_response:
            logger.info(f"Idempotency key '{Idempotency_Key}' hit. Returning cached response.")
            return JSONResponse(content=json.loads(cached_response), status_code=200)

    sub_room = await asyncio.to_thread(storage_service.get_room, sub_room_id)
    if not sub_room or sub_room.owner_id != user_info.get("user_id"):
        raise NotFoundError("sub_room", sub_room_id)
    if sub_room.type != "sub":
        raise InvalidRequestError("Reviews can only be created from sub-rooms.")

    review_room_id, review_meta = await review_service.create_review_and_room(
        sub_room_id=sub_room_id,
        user_id=user_info["user_id"],
        review_request=review_request
    )

    trace_id = str(uuid.uuid4())
    logger.info(f"Starting review process for review {review_meta.review_id} with trace_id: {trace_id}")
    await review_service.start_review_process(
        review_id=review_meta.review_id,
        review_room_id=review_room_id,
        topic=review_request.topic,
        instruction=review_request.instruction,
        panelists=review_request.panelists,
        trace_id=trace_id,
    )

    if Idempotency_Key:
        response_json = review_meta.model_dump_json()
        await asyncio.to_thread(redis_client.set, f"idempotency:{Idempotency_Key}", response_json, ex=IDEMPOTENCY_KEY_TTL)
        logger.info(f"Cached response for idempotency key '{Idempotency_Key}'.")

    return review_meta

@router.get("/reviews", response_model=List[ReviewMeta])
async def get_reviews_by_room(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    cache_service: CacheService = Depends(get_cache_service),
) -> List[ReviewMeta]:
    """Get all reviews for a specific room, with caching."""
    room = await asyncio.to_thread(storage_service.get_room, room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise NotFoundError("room", room_id)
    
    cache_key = f"reviews:room:{room_id}"
    cached_reviews = await cache_service.get(cache_key)
    if cached_reviews:
        return [ReviewMeta(**r) for r in cached_reviews]

    reviews = await asyncio.to_thread(storage_service.get_reviews_by_room, room_id)
    if reviews:
        await cache_service.set(cache_key, [r.model_dump() for r in reviews])
    return reviews

@router.get("/reviews/{review_id}", response_model=ReviewMeta)
async def get_review(
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    cache_service: CacheService = Depends(get_cache_service),
) -> ReviewMeta:
    """Get review information, with caching."""
    cache_key = f"review:meta:{review_id}"
    cached_review = await cache_service.get(cache_key)
    if cached_review:
        return ReviewMeta(**cached_review)

    review = await asyncio.to_thread(storage_service.get_review_meta, review_id)
    if not review:
        raise NotFoundError("review", review_id)

    # Note: We don't check ownership here, assuming review_id is secret.
    # Add check if necessary.

    await cache_service.set(cache_key, review.model_dump())
    return review

@router.get("/reviews/{review_id}/events", response_model=List[ReviewEvent])
async def get_review_events(
    review_id: str,
    since: Optional[int] = None,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
):
    """Get review progress events."""
    events_data = await asyncio.to_thread(storage_service.get_review_events, review_id, since)
    return [ReviewEvent(**event) for event in events_data]

@router.get("/reviews/{review_id}/report", response_class=JSONResponse)
async def get_review_report(
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    cache_service: CacheService = Depends(get_cache_service),
) -> Dict[str, Any]:
    """Get the final consolidated review report, with caching."""
    cache_key = f"review:report:{review_id}"
    cached_report = await cache_service.get(cache_key)
    if cached_report:
        return create_success_response(data=cached_report)

    report = await asyncio.to_thread(storage_service.get_final_report, review_id)
    if not report:
        raise NotFoundError("report", review_id)

    await cache_service.set(cache_key, report)
    return create_success_response(data=report)
