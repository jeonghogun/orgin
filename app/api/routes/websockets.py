import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.api.dependencies import get_storage_service, require_auth_ws
from app.services.storage_service import StorageService
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        logger.info(f"WebSocket connected for room {room_id}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        logger.info(f"WebSocket disconnected from room {room_id}")

    async def broadcast(self, message: str, room_id: str):
        if room_id not in self.active_connections:
            return

        logger.info(f"Broadcasting to room {room_id}: {message[:100]}")
        failed_connections: list[WebSocket] = []
        for connection in list(self.active_connections[room_id]):
            try:
                await connection.send_text(message)
            except Exception as send_error:
                logger.warning(
                    "WebSocket send failed for room %s: %s",
                    room_id,
                    send_error,
                    exc_info=True,
                )
                failed_connections.append(connection)

        for connection in failed_connections:
            self.disconnect(connection, room_id)

manager = ConnectionManager()

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

        await manager.connect(websocket, room_id)
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


@router.websocket("/ws/reviews/{review_id}")
async def websocket_review_endpoint(websocket: WebSocket, review_id: str):
    storage_service: StorageService = get_storage_service()
    user_id = None
    try:
        user_id = await require_auth_ws(websocket)
        review = storage_service.get_review_meta(review_id)
        # Skip ownership check if AUTH_OPTIONAL is enabled
        if not settings.AUTH_OPTIONAL and not review:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"Auth failed for WS to review {review_id}: Review not found.")
            return

        # Use the review_id as the channel id for review websockets
        channel_id = review_id
        await manager.connect(websocket, channel_id)
        while True:
            await websocket.receive_text() # Keep connection alive

    except WebSocketDisconnect:
        manager.disconnect(websocket, review_id)
        logger.info(f"WebSocket for user {user_id} to review {review_id} disconnected.")
    except Exception as e:
        logger.error(f"Error in WebSocket for review {review_id}: {e}", exc_info=True)
        # Ensure connection is closed on error
        manager.disconnect(websocket, review_id)
