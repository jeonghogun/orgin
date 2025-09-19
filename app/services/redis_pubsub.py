import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.config.settings import get_effective_redis_url
from app.services.realtime_service import realtime_service

logger = logging.getLogger(__name__)

class RedisPubSubManager:
    def __init__(self):
        self.redis_client = None
        self._redis_url_signature = None
        self.pubsub = None
        self.is_running = False

    async def _get_redis_client(self):
        target_url = get_effective_redis_url()
        if not target_url:
            return None

        if not self.redis_client or self._redis_url_signature != target_url:
            if self.redis_client:
                try:
                    await self.redis_client.close()
                except Exception:
                    pass
            try:
                self.redis_client = redis.from_url(target_url, encoding="utf-8", decode_responses=True)
                self._redis_url_signature = target_url
            except RedisError as exc:
                logger.warning("Failed to initialize Redis Pub/Sub client at %s: %s", target_url, exc)
                self.redis_client = None
                self._redis_url_signature = None
        return self.redis_client

    async def publish(self, channel: str, message: str):
        """Publish a message to a Redis channel."""
        client = await self._get_redis_client()
        if not client:
            logger.info("Skipping Redis publish to %s because Redis is unavailable", channel)
            return
        await client.publish(channel, message)
        logger.info(f"Published to {channel}: {message[:100]}")

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[AsyncIterator[str]]:
        """Yield an async iterator of messages for the requested channel."""
        client = await self._get_redis_client()

        if not client:
            logger.warning("Redis is unavailable; yielding empty subscription for %s", channel)

            async def _empty_iterator() -> AsyncIterator[str]:
                if False:
                    yield ""  # pragma: no cover - ensures generator nature

            yield _empty_iterator()
            return

        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        stop_event = asyncio.Event()

        async def _reader():
            try:
                while not stop_event.is_set():
                    try:
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=1.0
                        )
                    except Exception as exc:  # pragma: no cover - defensive logging
                        logger.error(
                            "Error while reading from Redis Pub/Sub %s: %s",
                            channel,
                            exc,
                            exc_info=True,
                        )
                        await asyncio.sleep(1)
                        continue

                    if message is None:
                        continue

                    data = message.get("data")
                    if data is None:
                        continue

                    await queue.put(str(data))
            except asyncio.CancelledError:
                raise
            finally:
                await queue.put(None)

        reader_task = asyncio.create_task(_reader())

        async def _iterator() -> AsyncIterator[str]:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item

        try:
            yield _iterator()
        finally:
            stop_event.set()
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass

            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception as exc:  # pragma: no cover - cleanup safety
                logger.debug(
                    "Error while closing Redis pubsub for %s: %s", channel, exc, exc_info=True
                )

    async def _listener(self):
        """Listen for messages and broadcast to connected WebSockets."""
        client = await self._get_redis_client()
        if not client:
            logger.warning("Redis Pub/Sub listener could not start because Redis is unavailable")
            return
        self.pubsub = client.pubsub()
        # Subscribe to a pattern that matches all review channels
        await self.pubsub.psubscribe("review_*")
        logger.info("Redis Pub/Sub listener started.")
        self.is_running = True

        while self.is_running:
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    channel = message['channel']
                    review_id = channel.split('_', 1)[1]
                    data = message['data']
                    logger.info(f"Message received from Redis on {channel}, broadcasting to real-time channel {review_id}")
                    await realtime_service.broadcast_raw(review_id, data)
            except Exception as e:
                logger.error(f"Error in Redis Pub/Sub listener: {e}", exc_info=True)
                # Add a small delay to prevent rapid-fire errors
                await asyncio.sleep(1)

    def start_listener(self):
        """Start the Redis listener as a background task."""
        if not self.is_running:
            logger.info("Creating Redis Pub/Sub listener background task.")
            asyncio.create_task(self._listener())

    async def stop_listener(self):
        """Stop the Redis listener."""
        if self.is_running and self.pubsub:
            await self.pubsub.unsubscribe()
            if self.redis_client:
                await self.redis_client.close()
            self.is_running = False
            logger.info("Redis Pub/Sub listener stopped.")

    def publish_sync(self, channel: str, message: str):
        """Publish a message to a Redis channel synchronously for Celery workers."""
        import redis as sync_redis
        sync_client = None
        target_url = get_effective_redis_url()
        if not target_url:
            logger.info("Skipping synchronous Redis publish to %s because Redis is unavailable", channel)
            return
        try:
            # Create a new synchronous client for this operation.
            # This is not the most efficient way, but it's simple and avoids
            # managing a separate long-lived synchronous client.
            sync_client = sync_redis.from_url(target_url, encoding="utf-8", decode_responses=True)
            sync_client.publish(channel, message)
            logger.info(f"Published synchronously to {channel}: {message[:100]}")
        except Exception as e:
            logger.error(f"Failed to publish synchronously to {channel}: {e}", exc_info=True)
        finally:
            if sync_client:
                sync_client.close()

# Singleton instance
redis_pubsub_manager = RedisPubSubManager()
