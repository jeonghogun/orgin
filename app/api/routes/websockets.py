import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.api.dependencies import get_storage_service, require_auth_ws
from app.services.storage_service import StorageService
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])

class ConnectionLimitError(Exception):
    """Raised when a room has reached its concurrent connection limit."""


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.sse_listeners: dict[str, list[asyncio.Queue[str]]] = {}
        self._max_connections = max(settings.REALTIME_MAX_CONNECTIONS_PER_ROOM, 0)
        self._sse_queue_size = max(settings.REALTIME_MAX_SSE_QUEUE_SIZE, 0)
        self._send_timeout = max(settings.REALTIME_SEND_TIMEOUT_SECONDS, 0.1)
        self._send_retries = max(settings.REALTIME_SEND_MAX_RETRIES, 0)
        self._retry_backoff = max(settings.REALTIME_SEND_RETRY_BACKOFF_SECONDS, 0.0)
        self._disconnect_on_backpressure = settings.REALTIME_DISCONNECT_ON_SLOW_CONSUMER

    async def connect(self, websocket: WebSocket, room_id: str):
        room_connections = self.active_connections.setdefault(room_id, [])
        if self._max_connections and len(room_connections) >= self._max_connections:
            logger.warning("Rejecting connection to %s - limit of %s reached", room_id, self._max_connections)
            raise ConnectionLimitError("Room has reached its connection capacity.")

        await websocket.accept()
        room_connections.append(websocket)
        logger.info(f"WebSocket connected for room {room_id}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        logger.info(f"WebSocket disconnected from room {room_id}")

    def register_sse_listener(self, channel_id: str) -> asyncio.Queue[str]:
        """Register an asyncio queue as an SSE listener for the given channel."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._sse_queue_size)
        listeners = self.sse_listeners.setdefault(channel_id, [])
        listeners.append(queue)
        return queue

    def unregister_sse_listener(self, channel_id: str, queue: asyncio.Queue[str]) -> None:
        listeners = self.sse_listeners.get(channel_id)
        if not listeners:
            return
        try:
            listeners.remove(queue)
        except ValueError:
            pass
        if not listeners:
            self.sse_listeners.pop(channel_id, None)

    async def _send_with_retry(self, connection: WebSocket, message: str) -> bool:
        attempts = self._send_retries + 1
        for attempt in range(attempts):
            try:
                await asyncio.wait_for(connection.send_text(message), timeout=self._send_timeout)
                return True
            except asyncio.TimeoutError:
                logger.warning(
                    "Timed out sending message to slow consumer in %s (attempt %s/%s)",
                    connection.client,
                    attempt + 1,
                    attempts,
                )
            except Exception as send_error:
                logger.warning(
                    "WebSocket send failed: %s", send_error, exc_info=True
                )

            if attempt < attempts - 1 and self._retry_backoff:
                await asyncio.sleep(self._retry_backoff)

        return False

    async def broadcast(self, message: str, room_id: str):
        logger.info(f"Broadcasting to room {room_id}: {message[:100]}")

        # Broadcast to WebSocket clients first
        connections = self.active_connections.get(room_id, [])
        if connections:
            results = await asyncio.gather(
                *(self._send_with_retry(connection, message) for connection in list(connections)),
                return_exceptions=True,
            )

            for connection, result in zip(list(connections), results):
                disconnect = False
                if isinstance(result, Exception):
                    logger.error("Broadcast task errored for room %s: %s", room_id, result, exc_info=True)
                    disconnect = True
                elif result is False:
                    logger.warning("Dropping slow WebSocket consumer in room %s", room_id)
                    disconnect = self._disconnect_on_backpressure

                if disconnect:
                    self.disconnect(connection, room_id)

        # Fan-out to SSE listeners as well
        for listener in list(self.sse_listeners.get(room_id, [])):
            try:
                listener.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Dropping SSE listener for %s due to full queue", room_id)
                self.unregister_sse_listener(room_id, listener)

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
        # Skip ownership check if AUTH_OPTIONAL is enabled
        if not settings.AUTH_OPTIONAL and not review:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"Auth failed for WS to review {review_id}: Review not found.")
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
