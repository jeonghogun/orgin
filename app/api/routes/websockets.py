import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.api.dependencies import get_storage_service, require_auth_ws
from app.services.storage_service import StorageService

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
        if room_id in self.active_connections:
            logger.info(f"Broadcasting to room {room_id}: {message[:100]}")
            for connection in self.active_connections[room_id]:
                await connection.send_text(message)

manager = ConnectionManager()

@router.websocket("/ws/reviews/{review_id}")
async def websocket_endpoint(websocket: WebSocket, review_id: str):
    storage_service: StorageService = get_storage_service()
    user_id = None
    try:
        user_id = await require_auth_ws(websocket)
        review = await storage_service.get_review_meta(review_id)
        if not review:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"Auth failed for WS to review {review_id}: Review not found.")
            return

        room = await storage_service.get_room(review.room_id)
        if not room or room.owner_id != user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"Auth failed for WS to review {review_id}: User {user_id} does not own room {review.room_id}.")
            return

        await manager.connect(websocket, review_id)
        while True:
            await websocket.receive_text() # Keep connection alive

    except WebSocketDisconnect:
        manager.disconnect(websocket, review_id)
        logger.info(f"WebSocket for user {user_id} to review {review_id} disconnected.")
    except Exception as e:
        logger.error(f"Error in WebSocket for review {review_id}: {e}", exc_info=True)
        # Ensure connection is closed on error
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        manager.disconnect(websocket, review_id)
