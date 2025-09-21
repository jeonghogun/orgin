import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.api.dependencies import get_storage_service, require_auth_ws
from app.core.realtime import ConnectionLimitError, connection_manager
from app.services.storage_service import StorageService
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])


manager = connection_manager

@router.websocket("/ws/rooms/{room_id}")
async def websocket_room_endpoint(websocket: WebSocket, room_id: str):
    storage_service: StorageService = get_storage_service()
    user_id = None
    try:
        user_id = await require_auth_ws(websocket)
        room = storage_service.get_room(room_id)
        # Skip ownership check if AUTH_OPTIONAL is enabled
        if not settings.AUTH_OPTIONAL and (not room or room.owner_id != user_id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"Auth failed for WS to room {room_id}: User {user_id} does not own room.")
            return

        try:
            await manager.connect(websocket, room_id)
        except ConnectionLimitError as limit_error:
            logger.warning("Room %s connection rejected: %s", room_id, limit_error)
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return
        while True:
            # Keep connection alive, but also handle potential client messages if needed in the future
            data = await websocket.receive_text()
            logger.debug(f"Received from {user_id} in room {room_id}: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        logger.info(f"WebSocket for user {user_id} to room {room_id} disconnected.")
    except Exception as e:
        logger.error(f"Error in WebSocket for room {room_id}: {e}", exc_info=True)
        manager.disconnect(websocket, room_id)


@router.websocket("/api/ws/rooms/{room_id}")
async def websocket_room_endpoint_with_api_prefix(websocket: WebSocket, room_id: str):
    await websocket_room_endpoint(websocket, room_id)


@router.websocket("/ws/reviews/{review_id}")
async def websocket_review_endpoint(websocket: WebSocket, review_id: str):
    storage_service: StorageService = get_storage_service()
    user_id = None
    try:
        user_id = await require_auth_ws(websocket)
        review = storage_service.get_review_meta(review_id)

        if not review:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"Auth failed for WS to review {review_id}: Review not found.")
            return

        review_room = storage_service.get_room(review.room_id)
        if not review_room:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(
                "Auth failed for WS to review %s: Review room %s not found.",
                review_id,
                review.room_id,
            )
            return

        # Skip ownership check only if AUTH_OPTIONAL is enabled
        if not settings.AUTH_OPTIONAL and review_room.owner_id != user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(
                "Auth failed for WS to review %s: User %s does not own room %s.",
                review_id,
                user_id,
                review.room_id,
            )
            return

        # Use the review_id as the channel id for review websockets
        channel_id = review_id
        try:
            await manager.connect(websocket, channel_id)
        except ConnectionLimitError as limit_error:
            logger.warning("Review channel %s connection rejected: %s", review_id, limit_error)
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return
        while True:
            await websocket.receive_text() # Keep connection alive

    except WebSocketDisconnect:
        manager.disconnect(websocket, review_id)
        logger.info(f"WebSocket for user {user_id} to review {review_id} disconnected.")
    except Exception as e:
        logger.error(f"Error in WebSocket for review {review_id}: {e}", exc_info=True)
        # Ensure connection is closed on error
        manager.disconnect(websocket, review_id)


@router.websocket("/api/ws/reviews/{review_id}")
async def websocket_review_endpoint_with_api_prefix(websocket: WebSocket, review_id: str):
    await websocket_review_endpoint(websocket, review_id)
