import asyncio
import logging
import redis.asyncio as redis
from app.config.settings import settings
from app.api.routes.websockets import manager as websocket_manager

logger = logging.getLogger(__name__)

class RedisPubSubManager:
    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self.is_running = False

    async def _get_redis_client(self):
        if not self.redis_client:
            self.redis_client = await redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        return self.redis_client

    async def publish(self, channel: str, message: str):
        """Publish a message to a Redis channel."""
        client = await self._get_redis_client()
        await client.publish(channel, message)
        logger.info(f"Published to {channel}: {message[:100]}")

    async def _listener(self):
        """Listen for messages and broadcast to connected WebSockets."""
        client = await self._get_redis_client()
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
                    logger.info(f"Message received from Redis on {channel}, broadcasting to WebSocket room {review_id}")
                    await websocket_manager.broadcast(data, review_id)
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
            await self.redis_client.close()
            self.is_running = False
            logger.info("Redis Pub/Sub listener stopped.")

# Singleton instance
redis_pubsub_manager = RedisPubSubManager()
