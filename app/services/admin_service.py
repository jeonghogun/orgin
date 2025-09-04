"""
Service for administrative-level operations and data retrieval.
"""
import logging
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timedelta

from app.services.database_service import DatabaseService, get_database_service
from app.models.schemas import ApiPanelistConfig as PanelistConfig # Assuming this is the right schema

logger = logging.getLogger(__name__)

class AdminService:
    def __init__(self, db_service: DatabaseService):
        self.db = db_service

    # Provider Config Methods
    async def get_provider_configs(self) -> List[Dict[str, Any]]:
        query = "SELECT * FROM provider_configs"
        return self.db.execute_query(query)

    async def update_provider_config(self, provider_name: str, config: Dict[str, Any]) -> None:
        query = """
            UPDATE provider_configs
            SET model = %s, timeout_ms = %s, retries = %s, enabled = %s, updated_at = NOW()
            WHERE provider_name = %s
        """
        params = (config['model'], config['timeout_ms'], config['retries'], config['enabled'], provider_name)
        self.db.execute_update(query, params)

    # System Settings Methods
    async def get_system_settings(self) -> Dict[str, Any]:
        query = "SELECT key, value_json FROM system_settings"
        results = self.db.execute_query(query)
        return {row['key']: row['value_json'] for row in results}

    async def update_system_setting(self, key: str, value: Any) -> None:
        query = """
            INSERT INTO system_settings (key, value_json, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET
                value_json = EXCLUDED.value_json,
                updated_at = NOW();
        """
        params = (key, json.dumps(value))
        self.db.execute_update(query, params)

    # Dashboard Methods
    async def get_dashboard_kpis(self) -> Dict[str, Any]:
        # Placeholder for complex KPI query logic
        return {
           "date": datetime.utcnow().strftime("%Y-%m-%d"),
           "reviews_today": 0,
           "success_rate": 1.0,
           "latency_p95_ms": 0,
           "tokens_prompt_today": 0,
           "tokens_completion_today": 0,
           "tokens_total_today": 0,
           "cost_estimate_usd_today": 0.0,
           "budget_today_usd": 0.0,
           "budget_used_ratio": 0.0,
           "provider_alerts": []
        }

# Singleton
_admin_service_instance: Optional[AdminService] = None

def get_admin_service() -> AdminService:
    global _admin_service_instance
    if _admin_service_instance is None:
        _admin_service_instance = AdminService(db_service=get_database_service())
    return _admin_service_instance
