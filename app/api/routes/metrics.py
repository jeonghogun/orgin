"""
Metrics-related API endpoints
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
import numpy as np

from app.services.storage_service import storage_service
from app.api.dependencies import AUTH_DEPENDENCY

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("")
async def get_metrics(
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    limit: int = 100,
    since: Optional[int] = None
):
    """Get aggregated review metrics."""
    try:
        # In a real app, we'd filter by user, but for now, we get all.
        all_metrics = await storage_service.get_all_review_metrics(limit=limit, since=since)

        if not all_metrics:
            return {"summary": "No metrics found.", "data": []}

        # Calculate aggregations
        total_reviews = len(all_metrics)
        durations = [m.total_duration_seconds for m in all_metrics]
        tokens = [m.total_tokens_used for m in all_metrics]

        summary = {
            "total_reviews": total_reviews,
            "avg_duration": np.mean(durations),
            "median_duration": np.median(durations),
            "p95_duration": np.percentile(durations, 95),
            "avg_tokens": np.mean(tokens),
            "median_tokens": np.median(tokens),
            "p95_tokens": np.percentile(tokens, 95),
        }

        return {"summary": summary, "data": all_metrics}

    except Exception as e:
        logger.error(f"Error getting metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get metrics")

@router.get("/alerts")
async def get_alerts(user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get the latest system alerts."""
    from app.tasks.review_tasks import latest_alerts
    return {"alerts": latest_alerts}
