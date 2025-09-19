import celery
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
    def storage_service(self) -> StorageService:
        """Lazily initialized StorageService instance."""
        cached = getattr(self, "_storage_service_instance", None)
        cached_cls = getattr(self, "_storage_service_cls_marker", None)
        if cached is None or cached_cls is not StorageService:
            cached = StorageService(env_secrets_provider)
            self._storage_service_instance = cached
            self._storage_service_cls_marker = StorageService
        return cached

    @property
    def llm_service(self) -> LLMService:
        """Lazily initialized LLMService instance."""
        cached = getattr(self, "_llm_service_instance", None)
        cached_cls = getattr(self, "_llm_service_cls_marker", None)
        if cached is None or cached_cls is not LLMService:
            cached = LLMService(env_secrets_provider)
            self._llm_service_instance = cached
            self._llm_service_cls_marker = LLMService
        return cached


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
