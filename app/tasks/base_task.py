import celery
from functools import lru_cache

from app.core.secrets import env_secrets_provider
from app.services.llm_service import LLMService
from app.services.storage_service import StorageService
from app.services.database_service import get_database_service
from app.services.cache_service import CacheService, get_sync_redis_client

class BaseTask(celery.Task):
    """
    A base task for Celery that provides convenient access to services.
    Services are instantiated lazily and cached per task instance for sync contexts.
    """

    @property
    @lru_cache(maxsize=None)
    def cache_service(self) -> CacheService:
        """Lazily initialized sync-only CacheService instance."""
        return CacheService(sync_redis_client=get_sync_redis_client())

    @property
    @lru_cache(maxsize=None)
    def storage_service(self) -> StorageService:
        """Lazily initialized StorageService instance."""
        return StorageService(
            db_service=get_database_service(),
            secret_provider=env_secrets_provider,
            cache_service=self.cache_service
        )

    @property
    @lru_cache(maxsize=None)
    def llm_service(self) -> LLMService:
        """Lazily initialized LLMService instance."""
        return LLMService(secret_provider=env_secrets_provider)
