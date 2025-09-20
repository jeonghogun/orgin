"""Review-related API endpoints."""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.dependencies import AUTH_DEPENDENCY, get_storage_service, get_review_service
from app.models.schemas import ReviewMeta
from app.services.storage_service import StorageService
from app.services.review_service import ReviewService
from app.utils.helpers import (
    create_success_response,
    generate_id,
    get_current_timestamp,
    maybe_await,
)
from app.models.enums import RoomType

logger = logging.getLogger(__name__)

# Unified realtime helpers expect normalized payloads.
def _format_review_event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize persisted review events into a consistent envelope."""
    raw_content = event.get("content")
    payload: Dict[str, Any] = {}
    if isinstance(raw_content, str) and raw_content:
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            payload = {"message": raw_content}
    elif isinstance(raw_content, dict):
        payload = raw_content

    meta = {
        "ts": event.get("ts"),
        "round": event.get("round"),
        "actor": event.get("actor"),
        "review_id": event.get("review_id"),
    }

    return {
        "type": event.get("type", "unknown"),
        "payload": payload,
        "meta": {k: v for k, v in meta.items() if v is not None},
    }


def _parse_live_review_message(message: str) -> Dict[str, Any]:
    """Parse Redis Pub/Sub payloads into the realtime envelope schema."""
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return {"type": "unknown", "payload": {"raw": message}, "meta": {}}

    payload = parsed.get("payload") or {}
    meta = {
        "ts": parsed.get("ts"),
        "review_id": parsed.get("review_id"),
        "version": parsed.get("version"),
    }

    return {
        "type": parsed.get("type", "unknown"),
        "payload": payload,
        "meta": {k: v for k, v in meta.items() if v is not None},
    }


# Create router
router = APIRouter(tags=["reviews"])

IDEMPOTENCY_KEY_TTL = 60 * 60 * 24  # 24 hours


class CreateReviewRequest(BaseModel):
    topic: str
    instruction: Optional[str] = None
    panelists: Optional[List[str]] = None


class ReviewStatusEvent(BaseModel):
    ts: Optional[int]
    status: str


class ReviewStatusResponse(BaseModel):
    review_id: str
    status: str
    current_round: int
    total_rounds: int
    fallback_active: bool
    has_report: bool
    status_history: List[ReviewStatusEvent]
    last_event: Optional[ReviewStatusEvent] = None


async def _maybe_get_room(storage_service: StorageService, room_id: str):
    return await asyncio.to_thread(storage_service.get_room, room_id)


@router.get("/reviews", response_model=List[ReviewMeta])
async def get_reviews_by_room(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
) -> List[ReviewMeta]:
    """Get all reviews for a specific room"""
    # Verify room exists and belongs to user
    room = await _maybe_get_room(storage_service, room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=404, detail="Room not found or access denied.")

    reviews = await asyncio.to_thread(storage_service.get_reviews_by_room, room_id)
    return reviews


@router.get("/rooms/{room_id}/reviews", response_model=List[ReviewMeta])
async def get_room_reviews(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
) -> List[ReviewMeta]:
    """Compatibility endpoint for nested room review queries."""
    return await get_reviews_by_room(room_id, user_info, storage_service)


@router.post("/rooms/{room_id}/reviews", response_model=ReviewMeta)
async def create_review_for_room(
    room_id: str,
    request: CreateReviewRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    review_service: ReviewService = Depends(get_review_service),
):
    user_id = user_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    parent_room = await _maybe_get_room(storage_service, room_id)
    if not parent_room:
        raise HTTPException(status_code=404, detail="Room not found")
    if parent_room.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot start a review in another user's room")
    if parent_room.type != RoomType.SUB:
        raise HTTPException(status_code=400, detail="Reviews can only be created from sub-rooms")

    review_room_id = generate_id("room")
    review_id = generate_id("rev")
    created_at = get_current_timestamp()
    instruction = request.instruction or "이 주제를 바탕으로 심층 검토를 진행해주세요."

    try:
        await asyncio.to_thread(
            storage_service.create_room,
            room_id=review_room_id,
            name=f"Review: {request.topic}",
            owner_id=user_id,
            room_type=RoomType.REVIEW,
            parent_id=room_id,
        )
    except Exception as create_error:
        logger.error("Failed to create review room for %s: %s", room_id, create_error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create review room")

    review_meta = ReviewMeta(
        review_id=review_id,
        room_id=review_room_id,
        topic=request.topic,
        instruction=instruction,
        status="pending",
        total_rounds=4,
        current_round=0,
        created_at=created_at,
    )

    try:
        await asyncio.to_thread(storage_service.save_review_meta, review_meta)
    except Exception as save_error:
        logger.error("Failed to persist review metadata for %s: %s", review_id, save_error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to persist review metadata")

    trace_id = str(uuid.uuid4())
    try:
        await maybe_await(
            review_service.start_review_process(
                review_id=review_id,
                review_room_id=review_room_id,
                topic=request.topic,
                instruction=instruction,
                panelists=request.panelists,
                trace_id=trace_id,
            )
        )
    except Exception as start_error:
        logger.error("Failed to start review %s: %s", review_id, start_error, exc_info=True)
        # Allow client to poll later; status remains pending

    return review_meta


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
    review = await asyncio.to_thread(storage_service.get_review_meta, id)

    # If not found, try fetching by room_id
    if not review:
        review = await asyncio.to_thread(storage_service.get_review_meta_by_room_id, id)

    # If still not found, or if found but owner doesn't match, raise error
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Verify that the associated room belongs to the user
    room = await _maybe_get_room(storage_service, review.room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied to review")

    if review.status != "completed":
        final_report = await asyncio.to_thread(
            storage_service.get_final_report, review.review_id
        )
        if final_report:
            try:
                await asyncio.to_thread(
                    storage_service.update_review,
                    review.review_id,
                    {"status": "completed"},
                )
                review.status = "completed"
            except Exception as sync_error:
                logger.warning(
                    "Failed to synchronise review %s status with final report: %s",
                    review.review_id,
                    sync_error,
                )

    return review


@router.get("/reviews/{review_id}/status", response_model=ReviewStatusResponse)
async def get_review_status_summary(
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),
    review_service: ReviewService = Depends(get_review_service),
) -> ReviewStatusResponse:
    """Return a snapshot of the asynchronous review workflow status."""

    review_meta = await asyncio.to_thread(storage_service.get_review_meta, review_id)
    if not review_meta:
        raise HTTPException(status_code=404, detail="Review not found")

    room = await _maybe_get_room(storage_service, review_meta.room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied to review")

    snapshot = await asyncio.to_thread(review_service.get_status_overview, review_id)
    history = [ReviewStatusEvent(**event) for event in snapshot.get("status_history", [])]
    last_event_payload = snapshot.get("last_event")
    last_event = ReviewStatusEvent(**last_event_payload) if last_event_payload else None

    return ReviewStatusResponse(
        review_id=snapshot.get("review_id", review_id),
        status=snapshot.get("status", review_meta.status),
        current_round=snapshot.get("current_round", review_meta.current_round or 0),
        total_rounds=snapshot.get("total_rounds", review_meta.total_rounds),
        fallback_active=snapshot.get("fallback_active", False),
        has_report=snapshot.get("has_report", False),
        status_history=history,
        last_event=last_event,
    )


from sse_starlette.sse import EventSourceResponse
from app.services.realtime_service import realtime_service

async def review_event_generator(
    review_id: str,
    request: Request,
    storage_service: StorageService,
):
    """
    Yields server-sent events for a specific review's progress.
    Listens to a Redis Pub/Sub channel.
    """
    # First, send all historical events for this review
    historical_events = await asyncio.to_thread(
        storage_service.get_review_events, review_id
    )
    for event in historical_events:
        payload = _format_review_event_payload(event)
        yield dict(
            event="historical_event",
            data=realtime_service.format_event(
                payload["type"],
                payload["payload"],
                {**payload["meta"], "delivery": "historical"},
            ),
        )

    listener_queue = realtime_service.register_listener(review_id)

    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(listener_queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield {
                    "event": "heartbeat",
                    "data": realtime_service.format_event(
                        "heartbeat",
                        {"status": "alive"},
                        {"delivery": "live"},
                    ),
                }
                continue

            if message is None:
                continue

            structured = _parse_live_review_message(message)
            yield dict(
                event="live_event",
                data=realtime_service.format_event(
                    structured["type"],
                    structured["payload"],
                    {**structured["meta"], "delivery": "live"},
                ),
            )
    finally:
        realtime_service.unregister_listener(review_id, listener_queue)

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
    review = await asyncio.to_thread(storage_service.get_review_meta, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    room = await _maybe_get_room(storage_service, review.room_id)
    if not room or room.owner_id != user_info.get("user_id"):
        raise HTTPException(status_code=403, detail="Access denied to review")

    return EventSourceResponse(
        review_event_generator(review_id, request, storage_service)
    )


@router.get("/reviews/{review_id}/report", response_class=JSONResponse)
async def get_review_report(
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, Any]:
    """Get the final consolidated review report."""
    report = await asyncio.to_thread(storage_service.get_final_report, review_id)
    if not report:
        raise HTTPException(
            status_code=404, detail="Report not found. It may still be generating."
        )
    # The helper returns a Dict, which FastAPI automatically converts to a JSONResponse
    return create_success_response(data=report)
