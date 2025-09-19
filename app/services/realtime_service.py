"""Unified real-time broadcasting helpers for SSE and WebSocket consumers."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.api.routes.websockets import manager as connection_manager

logger = logging.getLogger(__name__)


class RealtimeService:
    """Provide a single abstraction for broadcasting real-time events."""

    def __init__(self, manager=connection_manager) -> None:  # pragma: no cover - simple wiring
        self._manager = manager

    @staticmethod
    def format_event(event_type: str, payload: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> str:
        """Create a canonical JSON payload for streaming events."""
        envelope: Dict[str, Any] = {
            "type": event_type,
            "payload": payload,
        }
        if meta:
            envelope["meta"] = meta
        return json.dumps(envelope)

    async def publish(self, channel: str, event_type: str, payload: Dict[str, Any], *, meta: Optional[Dict[str, Any]] = None) -> None:
        """Broadcast an event to all WebSocket and SSE listeners."""
        message = self.format_event(event_type, payload, meta)
        await self._manager.broadcast(message, channel)

    async def broadcast_raw(self, channel: str, raw_payload: str) -> None:
        """Broadcast a pre-formatted JSON payload to listeners."""
        await self._manager.broadcast(raw_payload, channel)

    def register_listener(self, channel: str):
        """Register an SSE listener queue for the given channel."""
        return self._manager.register_sse_listener(channel)

    def unregister_listener(self, channel: str, queue) -> None:
        """Unregister a previously registered SSE listener queue."""
        self._manager.unregister_sse_listener(channel, queue)


realtime_service = RealtimeService()


def get_realtime_service() -> RealtimeService:  # pragma: no cover - simple accessor
    return realtime_service
