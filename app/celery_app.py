from celery import Celery
from app.config.settings import settings

celery_app = Celery(
    "tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.review_tasks", "app.tasks.persona_tasks"],
)

celery_app.conf.update(
    task_track_started=True,
)
