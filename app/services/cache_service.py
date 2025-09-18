import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Optional, Any
import redis.asyncio as redis

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _normalize_for_json(value: Any) -> Any:
    """Normalize complex values into JSON-serialisable structures."""
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except TypeError:
            # model_dump may expect keyword arguments in older Pydantic versions
            return value.model_dump(exclude_none=False)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _normalize_for_json(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_for_json(item) for item in value]
    return value

class CacheService:
    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
        self.default_ttl = 300  # 5 minutes

    async def get(self, key: str) -> Optional[Any]:
        """Get data from cache."""
        if not self.redis:
            logger.info(f"Cache MISS for key: {key} (Redis not available)")
            return None
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
        if not self.redis:
            logger.info(f"Cache SET skipped for key: {key} (Redis not available)")
            return False
        try:
            ttl = ttl or self.default_ttl
            if hasattr(value, "model_dump_json"):
                value_to_cache = value.model_dump_json()
            else:
                normalized = _normalize_for_json(value)
                value_to_cache = json.dumps(normalized)

            await self.redis.setex(key, ttl, value_to_cache)
            logger.info(f"Cache SET for key: {key} with TTL: {ttl}")
            return True
        except Exception as e:
            logger.error(f"Cache set failed for key {key}: {e}", exc_info=True)
            return False

    async def delete(self, key: str) -> bool:
        """Delete data from cache."""
        if not self.redis:
            logger.info(f"Cache DELETE skipped for key: {key} (Redis not available)")
            return False
        try:
            await self.redis.delete(key)
            logger.info(f"Cache DELETE for key: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete failed for key {key}: {e}", exc_info=True)
            return False

_redis_client: Optional[redis.Redis] = None

async def get_redis_client() -> Optional[redis.Redis]:
    """Get a singleton Redis client instance."""
    global _redis_client
    if _redis_client is None and settings.REDIS_URL:
        try:
            # Ensure the client is created with decode_responses=True for string operations
            _redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        except Exception as e:
            logger.error(f"Failed to create Redis client for cache: {e}")
            _redis_client = None
    return _redis_client

async def get_cache_service() -> CacheService:
    """Dependency provider for CacheService."""
    redis_client = await get_redis_client()
    return CacheService(redis_client)
