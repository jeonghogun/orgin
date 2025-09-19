"""Service for calculating and storing Key Performance Indicators (KPIs)."""

import json
import logging
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Optional

from app.services.database_service import DatabaseService, get_database_service

logger = logging.getLogger(__name__)

class KPIService:
    """Service to handle KPI calculations and storage."""

    def __init__(self, db_service: DatabaseService):
        self.db = db_service

    async def calculate_and_store_daily_snapshot(self, snapshot_date: date):
        """
        Calculates all daily KPIs and stores them in the kpi_snapshots table.
        This is intended to be called by a scheduled Celery task.
        """
        logger.info(f"Calculating KPI snapshot for date: {snapshot_date}")

        # In a real implementation, each of these would be a complex SQL query.
        # For now, we'll use placeholder values.
        kpis = {
            "daily_active_users": 100,
            "weekly_active_users": 500,
            "monthly_active_users": 2000,
            "new_reviews_created": 20,
            "avg_review_cost": 0.05,
            "total_token_cost": 50.0,
        }

        for name, value in kpis.items():
            await self.save_snapshot(snapshot_date, name, value)

    async def save_snapshot(
        self,
        snapshot_date: date,
        metric_name: str,
        value: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Saves a single KPI value to the database."""
        query = """
            INSERT INTO kpi_snapshots (snapshot_date, metric_name, value, details)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (snapshot_date, metric_name) DO UPDATE SET
                value = EXCLUDED.value,
                details = EXCLUDED.details;
        """
        params = (snapshot_date, metric_name, value, json.dumps(details) if details else None)
        try:
            self.db.execute_update(query, params)
        except Exception as e:
            logger.error(f"Failed to save KPI snapshot for '{metric_name}': {e}")

    async def get_historical_kpis(self, start_date: date, end_date: date) -> Dict[str, list]:
        """Queries historical KPI data for the admin dashboard."""
        query = """
            SELECT snapshot_date, metric_name, value
            FROM kpi_snapshots
            WHERE snapshot_date >= %s AND snapshot_date <= %s
            ORDER BY snapshot_date ASC
        """
        params = (start_date, end_date)
        results = self.db.execute_query(query, params)

        # Pivot the data for easy charting on the frontend
        pivoted_data = defaultdict(lambda: {"dates": [], "values": []})
        for row in results:
            metric = row["metric_name"]
            pivoted_data[metric]["dates"].append(row["snapshot_date"].isoformat())
            pivoted_data[metric]["values"].append(row["value"])

        return pivoted_data

# Singleton instance
_kpi_service_instance: Optional[KPIService] = None

def get_kpi_service() -> KPIService:
    global _kpi_service_instance
    if _kpi_service_instance is None:
        _kpi_service_instance = KPIService(db_service=get_database_service())
    return _kpi_service_instance
