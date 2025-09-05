"""
Service for logging administrator actions.
"""
import logging
import json
import time
from typing import Dict, Any, Optional

from app.services.database_service import DatabaseService, get_database_service

logger = logging.getLogger(__name__)

class AuditService:
    """Service to handle writing audit trail events."""

    def __init__(self, db_service: DatabaseService):
        self.db = db_service

    async def log_action(
        self,
        admin_user_id: str,
        action: str,
        details: Dict[str, Any]
    ):
        """Logs an administrative action to the audit_logs table."""
        query = """
            INSERT INTO audit_logs (timestamp, admin_user_id, action, details)
            VALUES (%s, %s, %s, %s)
        """
        params = (
            int(time.time()),
            admin_user_id,
            action,
            json.dumps(details)
        )
        try:
            self.db.execute_update(query, params)
            logger.info(f"Audit log: User '{admin_user_id}' performed action '{action}'.")
        except Exception as e:
            logger.error(f"Failed to write to audit log: {e}")
            # In a real system, this failure might trigger a critical alert,
            # as failing to audit is a serious security event.
            pass

# Singleton instance (though it might be better to inject this via dependencies)
_audit_service_instance: Optional[AuditService] = None

def get_audit_service() -> AuditService:
    global _audit_service_instance
    if _audit_service_instance is None:
        _audit_service_instance = AuditService(db_service=get_database_service())
    return _audit_service_instance
