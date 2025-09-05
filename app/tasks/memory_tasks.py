"""
Celery tasks for memory management, including archival and summarization.
"""
import logging
from datetime import date, timedelta
from asgiref.sync import async_to_sync
from celery.schedules import crontab

from app.celery_app import celery_app
from app.services.memory_service import get_memory_service
from app.services.storage_service import get_storage_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Sets up the periodic task schedule."""
    # Run daily at 01:00 UTC to archive old memories
    sender.add_periodic_task(
        crontab(hour=1, minute=0),
        archive_all_rooms.s(),
        name='Archive old memories for all rooms'
    )
    # Run weekly on Sunday at 02:00 UTC to create summaries
    sender.add_periodic_task(
        crontab(hour=2, minute=0, day_of_week='sunday'),
        summarize_all_rooms_weekly.s(),
        name='Generate weekly summaries for all rooms'
    )

@celery_app.task
def archive_all_rooms():
    """Iterates through all rooms and triggers archival for each."""
    logger.info("Starting daily memory archival for all rooms.")
    storage = get_storage_service()
    all_rooms = async_to_sync(storage.get_all_rooms)() # Assumes this method exists
    for room in all_rooms:
        archive_old_memories_task.delay(room.room_id)

@celery_app.task
def summarize_all_rooms_weekly():
    """Iterates through all rooms and triggers weekly summarization."""
    logger.info("Starting weekly summary generation for all rooms.")
    storage = get_storage_service()
    all_rooms = async_to_sync(storage.get_all_rooms)()
    for room in all_rooms:
        weekly_room_summary_task.delay(room.room_id)

@celery_app.task
def archive_old_memories_task(room_id: str):
    """
    Finds messages outside the recent memory window, summarizes them,
    stores them as a long-term memory, and deletes the originals.
    """
    logger.info(f"Running archival task for room_id: {room_id}")
    memory_service = get_memory_service()
    # This is a placeholder for the complex logic of fetching, summarizing,
    # and deleting old messages based on settings.
    async_to_sync(memory_service.archive_old_memories)(room_id)

@celery_app.task
def weekly_room_summary_task(room_id: str):
    """
    Summarizes the last 7 days of conversation in a room.
    """
    logger.info(f"Running weekly summary task for room_id: {room_id}")
    # Placeholder for the summarization logic.
    pass
