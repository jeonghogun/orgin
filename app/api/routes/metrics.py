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

from collections import defaultdict

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
        all_metrics: List[ReviewMetrics] = await storage_service.get_all_review_metrics(
            limit=limit, since=since
        )

        if not all_metrics:
            return MetricsResponse(summary=MetricsSummary(total_reviews=0), data=[])

        # Calculate overall aggregations
        durations = [m.total_duration_seconds for m in all_metrics]
        tokens = [m.total_tokens_used for m in all_metrics]

        # Calculate per-provider aggregations
        provider_summary = defaultdict(lambda: {"total_calls": 0, "total_success": 0, "total_failures": 0, "total_tokens": 0, "total_duration": 0.0})
        for m in all_metrics:
            for provider, stats in m.provider_metrics.items():
                provider_summary[provider]["total_calls"] += stats.get("success", 0) + stats.get("fail", 0)
                provider_summary[provider]["total_success"] += stats.get("success", 0)
                provider_summary[provider]["total_failures"] += stats.get("fail", 0)
                provider_summary[provider]["total_tokens"] += stats.get("total_tokens", 0)
                provider_summary[provider]["total_duration"] += stats.get("duration", 0)

        # Finalize provider summary with averages
        final_provider_summary = {}
        for provider, data in provider_summary.items():
            total_calls = data["total_calls"]
            final_provider_summary[provider] = {
                "total_calls": total_calls,
                "success_rate": (data["total_success"] / total_calls) if total_calls > 0 else 0,
                "avg_tokens": (data["total_tokens"] / total_calls) if total_calls > 0 else 0,
                "avg_duration": (data["total_duration"] / total_calls) if total_calls > 0 else 0,
            }

        summary = MetricsSummary(
            total_reviews=len(all_metrics),
            avg_duration=float(np.mean(durations)) if durations else 0,
            median_duration=float(np.median(durations)) if durations else 0,
            p95_duration=float(np.percentile(durations, 95)) if durations else 0,
            avg_tokens=float(np.mean(tokens)) if tokens else 0,
            median_tokens=float(np.median(tokens)) if tokens else 0,
            p95_tokens=float(np.percentile(tokens, 95)) if tokens else 0,
            provider_summary=final_provider_summary,
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
