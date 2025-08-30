import logging
from datetime import date, timedelta
from asgiref.sync import async_to_sync
from celery.schedules import crontab

from app.celery_app import celery_app
from app.services.kpi_service import get_kpi_service

logger = logging.getLogger(__name__)

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Sets up the periodic task schedule."""
    # Run daily at 00:05 UTC
    sender.add_periodic_task(
        crontab(hour=0, minute=5),
        generate_kpi_snapshot.s(),
        name='Generate daily KPI snapshot'
    )

@celery_app.task
def generate_kpi_snapshot():
    """A Celery task to generate and store the daily KPI snapshot."""
    logger.info("Triggering daily KPI snapshot generation.")
    kpi_service = get_kpi_service()
    today = date.today()
    # We run it for the previous day to ensure all data is final
    yesterday = today - timedelta(days=1)
    async_to_sync(kpi_service.calculate_and_store_daily_snapshot)(snapshot_date=yesterday)
