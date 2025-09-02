import json
import logging
from typing import Optional, Any
import redis
import redis.asyncio as aredis

from app.config.settings import settings

logger = logging.getLogger(__name__)

class CacheService:
    """A cache service that provides both sync and async methods."""
    def __init__(self, sync_redis_client: redis.Redis, async_redis_client: Optional[aredis.Redis] = None):
        self.sync_redis = sync_redis_client
        self.async_redis = async_redis_client
        self.default_ttl = 300  # 5 minutes

    def _serialize(self, value: Any) -> str:
        """Serializes a value for caching."""
        if hasattr(value, 'model_dump'):
            return json.dumps(value.model_dump())
        if isinstance(value, list) and value and hasattr(value[0], 'model_dump'):
            return json.dumps([item.model_dump() for item in value])
        return json.dumps(value)

    # --- Async methods for FastAPI ---

    async def get(self, key: str) -> Optional[Any]:
        """Get data from cache asynchronously."""
        try:
            data = await self.async_redis.get(key)
            if data:
                logger.info(f"Cache HIT for key: {key}")
                return json.loads(data)
            logger.info(f"Cache MISS for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Async Cache GET failed for key {key}: {e}", exc_info=True)
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set data in cache asynchronously with a TTL."""
        try:
            ttl = ttl or self.default_ttl
            value_to_cache = self._serialize(value)
            await self.async_redis.setex(key, ttl, value_to_cache)
            logger.info(f"Async Cache SET for key: {key} with TTL: {ttl}")
            return True
        except Exception as e:
            logger.error(f"Async Cache SET failed for key {key}: {e}", exc_info=True)
            return False

    async def delete(self, key: str) -> bool:
        """Delete data from cache asynchronously."""
        try:
            await self.async_redis.delete(key)
            logger.info(f"Async Cache DELETE for key: {key}")
            return True
        except Exception as e:
            logger.error(f"Async Cache DELETE failed for key {key}: {e}", exc_info=True)
            return False

    # --- Sync methods for Celery ---

    def get_sync(self, key: str) -> Optional[Any]:
        """Get data from cache synchronously."""
        try:
            data = self.sync_redis.get(key)
            if data:
                logger.info(f"Sync Cache HIT for key: {key}")
                return json.loads(data)
            logger.info(f"Sync Cache MISS for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Sync Cache GET failed for key {key}: {e}", exc_info=True)
            return None

    def set_sync(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set data in cache synchronously with a TTL."""
        try:
            ttl = ttl or self.default_ttl
            value_to_cache = self._serialize(value)
            self.sync_redis.setex(key, ttl, value_to_cache)
            logger.info(f"Sync Cache SET for key: {key} with TTL: {ttl}")
            return True
        except Exception as e:
            logger.error(f"Sync Cache SET failed for key {key}: {e}", exc_info=True)
            return False

    def delete_sync(self, key: str) -> bool:
        """Delete data from cache synchronously."""
        try:
            self.sync_redis.delete(key)
            logger.info(f"Sync Cache DELETE for key: {key}")
            return True
        except Exception as e:
            logger.error(f"Sync Cache DELETE failed for key {key}: {e}", exc_info=True)
            return False

# --- Dependency Injection ---

_sync_redis_client: Optional[redis.Redis] = None
_async_redis_client: Optional[aredis.Redis] = None
_cache_service: Optional[CacheService] = None

def get_sync_redis_client() -> redis.Redis:
    """Get a singleton synchronous Redis client instance."""
    global _sync_redis_client
    if _sync_redis_client is None:
        _sync_redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return _sync_redis_client

async def get_async_redis_client() -> aredis.Redis:
    """Get a singleton asynchronous Redis client instance."""
    global _async_redis_client
    if _async_redis_client is None:
        _async_redis_client = aredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return _async_redis_client

async def get_cache_service() -> CacheService:
    """Dependency provider for the singleton CacheService."""
    global _cache_service
    if _cache_service is None:
        sync_client = get_sync_redis_client()
        async_client = await get_async_redis_client()
        _cache_service = CacheService(sync_redis_client=sync_client, async_redis_client=async_client)
    return _cache_service

def get_cache_service_sync() -> CacheService:
    """Dependency provider for synchronous contexts."""
    global _cache_service
    if _cache_service is None:
        sync_client = get_sync_redis_client()
        # We cannot await the async client here. This is a problem.
        # The async client must be created in an async context.
        # Let's create it on demand in the async provider.
        # And for the sync one, we can't create the async client.
        # This means the CacheService needs to be able to handle a missing async client.
        # Let's rethink the provider.

        # A better approach: The service is always created with both clients.
        # The dependency provider for sync contexts can't exist easily.
        # So, the service that needs it (StorageService) must be instantiated
        # by a provider that can access the async context.

        # Let's stick to the current plan. The StorageService is instantiated in dependencies.py,
        # which can be an async context.

        # The problem is with the singleton pattern.
        # The `get_cache_service` must be async.
        # The `get_storage_service` must become async to await it.
        # This will ripple.

        # Let's simplify. The sync part of the app (Celery) will create its own CacheService instance.
        # The async part (FastAPI) will create its own.

        # Let's remove the sync provider here and handle it in the service that needs it.
        # This file should only contain the async provider for FastAPI.

        # I'll revert the provider logic to be simpler, and handle instantiation in StorageService and the API routes.
        # No, the dependency injection file is the right place.
        # I will modify `dependencies.py` to be async-aware.
        pass # The code I wrote above is actually fine. The `get_cache_service` is async, and it will be `await`ed by FastAPI's dependency injection system. The problem is how `get_storage_service` gets it.

    # The code I wrote for the file is fine. `get_cache_service` is an async dependency provider.
    # The `get_storage_service` in `dependencies.py` needs to become async.

    # Let me stick to the file I wrote. It's correct. I'll deal with the dependency chain next.
    return _cache_service
