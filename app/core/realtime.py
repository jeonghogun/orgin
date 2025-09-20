"""Realtime connection management utilities shared across WebSocket and SSE paths."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import WebSocket

from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RealtimeConfig:
    """Configuration used by :class:`ConnectionManager`."""

    max_connections: int
    sse_queue_size: int
    send_timeout: float
    send_retries: int
    retry_backoff: float
    disconnect_on_backpressure: bool

    @classmethod
    def from_settings(cls) -> "RealtimeConfig":
        return cls(
            max_connections=max(settings.REALTIME_MAX_CONNECTIONS_PER_ROOM, 0),
            sse_queue_size=max(settings.REALTIME_MAX_SSE_QUEUE_SIZE, 0),
            send_timeout=max(settings.REALTIME_SEND_TIMEOUT_SECONDS, 0.1),
            send_retries=max(settings.REALTIME_SEND_MAX_RETRIES, 0),
            retry_backoff=max(settings.REALTIME_SEND_RETRY_BACKOFF_SECONDS, 0.0),
            disconnect_on_backpressure=settings.REALTIME_DISCONNECT_ON_SLOW_CONSUMER,
        )


class ConnectionLimitError(Exception):
    """Raised when a channel exceeds its concurrent connection limit."""


class ConnectionManager:
    def __init__(self, config: Optional[RealtimeConfig] = None) -> None:
        self._config = config or RealtimeConfig.from_settings()
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.sse_listeners: dict[str, list[asyncio.Queue[str]]] = {}

    @property
    def config(self) -> RealtimeConfig:
        return self._config

    async def connect(self, websocket: WebSocket, channel_id: str) -> None:
        room_connections = self.active_connections.setdefault(channel_id, [])
        if self.config.max_connections and len(room_connections) >= self.config.max_connections:
            logger.warning(
                "Rejecting connection to %s - limit of %s reached",
                channel_id,
                self.config.max_connections,
            )
            raise ConnectionLimitError("Channel has reached its connection capacity.")

        await websocket.accept()
        room_connections.append(websocket)
        logger.info("WebSocket connected for channel %s", channel_id)

    def disconnect(self, websocket: WebSocket, channel_id: str) -> None:
        if channel_id not in self.active_connections:
            return

        connections = self.active_connections[channel_id]
        try:
            connections.remove(websocket)
        except ValueError:
            return

        if not connections:
            del self.active_connections[channel_id]

        logger.info("WebSocket disconnected from channel %s", channel_id)

    def register_sse_listener(self, channel_id: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.config.sse_queue_size)
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
        attempts = self.config.send_retries + 1
        for attempt in range(attempts):
            try:
                await asyncio.wait_for(
                    connection.send_text(message),
                    timeout=self.config.send_timeout,
                )
                return True
            except asyncio.TimeoutError:
                logger.warning(
                    "Timed out sending message to slow consumer in %s (attempt %s/%s)",
                    connection.client,
                    attempt + 1,
                    attempts,
                )
            except Exception as send_error:  # pragma: no cover - defensive logging
                logger.warning(
                    "WebSocket send failed: %s",
                    send_error,
                    exc_info=True,
                )

            if attempt < attempts - 1 and self.config.retry_backoff:
                await asyncio.sleep(self.config.retry_backoff)

        return False

    async def broadcast(self, message: str, channel_id: str) -> None:
        logger.info("Broadcasting to %s: %s", channel_id, message[:100])

        connections = list(self.active_connections.get(channel_id, []))
        if connections:
            results = await asyncio.gather(
                *(self._send_with_retry(connection, message) for connection in connections),
                return_exceptions=True,
            )

            for connection, result in zip(connections, results):
                disconnect = False
                if isinstance(result, Exception):
                    logger.error(
                        "Broadcast task errored for %s: %s",
                        channel_id,
                        result,
                        exc_info=True,
                    )
                    disconnect = True
                elif result is False:
                    logger.warning(
                        "Dropping slow WebSocket consumer in %s",
                        channel_id,
                    )
                    disconnect = self.config.disconnect_on_backpressure

                if disconnect:
                    self.disconnect(connection, channel_id)

        for listener in list(self.sse_listeners.get(channel_id, [])):
            try:
                listener.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(
                    "Dropping SSE listener for %s due to full queue",
                    channel_id,
                )
                self.unregister_sse_listener(channel_id, listener)


# Shared singleton used by API routes and services
connection_manager = ConnectionManager()

__all__ = [
    "ConnectionManager",
    "ConnectionLimitError",
    "RealtimeConfig",
    "connection_manager",
]
