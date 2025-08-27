"""
Metrics-related API endpoints
"""

import logging
from typing import Dict, Optional, List, Any
from fastapi import APIRouter, HTTPException, Depends
import numpy as np

from app.services.storage_service import StorageService
from app.api.dependencies import require_auth, get_storage_service
from app.models.schemas import MetricsResponse, MetricsSummary, ReviewMetrics


logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
async def get_metrics(
    user_info: Dict[str, str] = Depends(require_auth),  # pyright: ignore[reportCallInDefaultInitializer]
    limit: int = 100,
    since: Optional[int] = None,
    storage_service: StorageService = Depends(get_storage_service),  # pyright: ignore[reportCallInDefaultInitializer]
) -> MetricsResponse:
    """Get aggregated review metrics."""
    try:
        # In a real app, we'd filter by user, but for now, we get all.
        all_metrics: List[ReviewMetrics] = await storage_service.get_all_review_metrics(
            limit=limit, since=since
        )

        if not all_metrics:
            summary = MetricsSummary(
                total_reviews=0,
                avg_duration=0.0,
                median_duration=0.0,
                p95_duration=0.0,
                avg_tokens=0.0,
                median_tokens=0.0,
                p95_tokens=0.0,
            )
            return MetricsResponse(summary=summary, data=[])

        # Calculate aggregations
        durations = [m.total_duration_seconds for m in all_metrics]
        tokens = [m.total_tokens_used for m in all_metrics]

        summary = MetricsSummary(
            total_reviews=len(all_metrics),
            avg_duration=float(np.mean(durations)),
            median_duration=float(np.median(durations)),
            p95_duration=float(np.percentile(durations, 95)),
            avg_tokens=float(np.mean(tokens)),
            median_tokens=float(np.median(tokens)),
            p95_tokens=float(np.percentile(tokens, 95)),
        )

        return MetricsResponse(summary=summary, data=all_metrics)

    except Exception as e:
        logger.error(f"Error getting metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@router.get("/alerts")
async def get_alerts(
    user_info: Dict[str, str] = Depends(require_auth),  # pyright: ignore[reportCallInDefaultInitializer]
) -> Dict[str, List[Dict[str, Any]]]:
    """Get the latest system alerts."""
    from app.tasks.review_tasks import latest_alerts

    return {"alerts": latest_alerts}
