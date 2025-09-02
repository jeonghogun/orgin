import json
import logging
from typing import Optional, Any
import redis.asyncio as redis

from app.config.settings import settings

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.default_ttl = 300  # 5 minutes

    async def get(self, key: str) -> Optional[Any]:
        """Get data from cache."""
        try:
            data = await self.redis.get(key)
            if data:
                logger.info(f"Cache HIT for key: {key}")
                return json.loads(data)
            logger.info(f"Cache MISS for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get failed for key {key}: {e}", exc_info=True)
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set data in cache with a TTL."""
        try:
            ttl = ttl or self.default_ttl
            # Use model_dump for Pydantic models before json.dumps
            if hasattr(value, 'model_dump_json'):
                value_to_cache = value.model_dump_json()
            elif isinstance(value, list) and hasattr(value[0], 'model_dump'):
                 value_to_cache = json.dumps([item.model_dump() for item in value])
            else:
                value_to_cache = json.dumps(value)

            await self.redis.setex(key, ttl, value_to_cache)
            logger.info(f"Cache SET for key: {key} with TTL: {ttl}")
            return True
        except Exception as e:
            logger.error(f"Cache set failed for key {key}: {e}", exc_info=True)
            return False

    async def delete(self, key: str) -> bool:
        """Delete data from cache."""
        try:
            await self.redis.delete(key)
            logger.info(f"Cache DELETE for key: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete failed for key {key}: {e}", exc_info=True)
            return False

_redis_client: Optional[redis.Redis] = None

async def get_redis_client() -> redis.Redis:
    """Get a singleton Redis client instance."""
    global _redis_client
    if _redis_client is None:
        try:
            # Ensure the client is created with decode_responses=True for string operations
            _redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        except Exception as e:
            logger.error(f"Failed to create Redis client for cache: {e}")
            raise
    return _redis_client

async def get_cache_service() -> CacheService:
    """Dependency provider for CacheService."""
    redis_client = await get_redis_client()
    return CacheService(redis_client)
