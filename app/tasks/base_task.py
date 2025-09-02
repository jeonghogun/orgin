import celery
from functools import lru_cache

from app.core.secrets import env_secrets_provider
from app.services.llm_service import LLMService
from app.services.storage_service import StorageService

class BaseTask(celery.Task):
    """
    A base task for Celery that provides convenient access to services.
    Services are instantiated lazily and cached per task instance.
    """

    @property
    @lru_cache(maxsize=None)
    def storage_service(self) -> StorageService:
        """Lazily initialized StorageService instance."""
        return StorageService(env_secrets_provider)

    @property
    @lru_cache(maxsize=None)
    def llm_service(self) -> LLMService:
        """Lazily initialized LLMService instance."""
        return LLMService(env_secrets_provider)
