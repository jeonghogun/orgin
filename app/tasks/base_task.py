import celery
from functools import lru_cache
from tenacity import retry, stop_after_attempt, wait_exponential

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


class BaseTaskWithRetries(BaseTask):
    """
    A base task for Celery that provides retry functionality with exponential backoff.
    Extends BaseTask with automatic retry capabilities.
    """
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when a task is retried."""
        super().on_retry(exc, task_id, args, kwargs, einfo)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when a task fails after all retries are exhausted."""
        super().on_failure(exc, task_id, args, kwargs, einfo)
