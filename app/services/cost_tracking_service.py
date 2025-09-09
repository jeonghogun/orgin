"""
Cost Tracking Service for monitoring API usage and costs.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class CostTrackingService:
    """Service for tracking API costs and usage."""
    
    def __init__(self):
        """Initialize the cost tracking service."""
        self.costs: Dict[str, float] = {}
        self.usage: Dict[str, int] = {}
    
    def track_api_call(self, provider: str, model: str, tokens_used: int, cost: float) -> None:
        """Track an API call and its cost."""
        key = f"{provider}:{model}"
        
        if key not in self.costs:
            self.costs[key] = 0.0
            self.usage[key] = 0
        
        self.costs[key] += cost
        self.usage[key] += tokens_used
        
        logger.info(f"Tracked API call: {key}, tokens: {tokens_used}, cost: ${cost:.4f}")
    
    def get_total_cost(self) -> float:
        """Get total cost across all providers."""
        return sum(self.costs.values())
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get usage summary."""
        return {
            "total_cost": self.get_total_cost(),
            "costs_by_provider": self.costs.copy(),
            "usage_by_provider": self.usage.copy(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def record_usage(self, user_id: str, tokens: int, model: str, cost: float) -> None:
        """Record usage for a specific user."""
        # For now, just track globally - can be extended to track per user
        self.track_api_call("openai", model, tokens, cost)
    
    def get_usage_stats(self, user_id: str) -> Dict[str, Any]:
        """Get usage statistics for a user."""
        return {
            "user_id": user_id,
            "total_tokens": sum(self.usage.values()),
            "total_cost": self.get_total_cost(),
            "usage_by_provider": self.usage.copy(),
            "costs_by_provider": self.costs.copy()
        }
    
    def reset_tracking(self) -> None:
        """Reset all tracking data."""
        self.costs.clear()
        self.usage.clear()
        logger.info("Cost tracking data reset")


# Global service instance
cost_tracking_service: Optional[CostTrackingService] = None


def get_cost_tracking_service() -> CostTrackingService:
    """Get the global cost tracking service instance."""
    global cost_tracking_service
    if cost_tracking_service is None:
        cost_tracking_service = CostTrackingService()
    return cost_tracking_service
