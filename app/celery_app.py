from celery import Celery
from app.config.settings import settings

celery_app = Celery(
    "tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.review_tasks", "app.tasks.persona_tasks"],
)

celery_app.conf.update(  # type: ignore
    task_track_started=True,
    result_extended=True,
)
