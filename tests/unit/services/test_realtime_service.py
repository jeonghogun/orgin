import asyncio
import json

import pytest

from app.api.routes.websockets import ConnectionManager
from app.services.realtime_service import RealtimeService


def test_broadcast_drops_full_sse_listener():
    manager = ConnectionManager()
    room_id = 'room-test'

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        loop.run_until_complete(queue.put('existing-message'))
        manager.sse_listeners[room_id] = [queue]

        loop.run_until_complete(manager.broadcast(json.dumps({'type': 'new_message'}), room_id))
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    assert room_id not in manager.sse_listeners or queue not in manager.sse_listeners.get(room_id, [])


def test_format_event_includes_meta():
    payload = {'value': 'test'}
    meta = {'delivery': 'live', 'attempt': 3}

    message = RealtimeService.format_event('heartbeat', payload, meta)
    parsed = json.loads(message)

    assert parsed['type'] == 'heartbeat'
    assert parsed['payload'] == payload
    assert parsed['meta']['delivery'] == 'live'
    assert parsed['meta']['attempt'] == 3
