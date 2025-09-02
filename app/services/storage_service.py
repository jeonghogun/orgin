"""
Storage Service - Unified interface for data persistence with cache invalidation.
This service is now fully synchronous.
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional, Literal, TypedDict

from app.models.enums import RoomType
from app.models.schemas import (
    Room, Message, ReviewMeta, ReviewFull, PanelReport, ConsolidatedReport, ReviewMetrics
)
from app.services.database_service import DatabaseService
from app.core.secrets import SecretProvider
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

class RoomRow(TypedDict):
    room_id: str
    name: str
    owner_id: str
    type: RoomType
    parent_id: Optional[str]
    created_at: int
    updated_at: int
    message_count: int

class MessageRow(TypedDict):
    message_id: str
    room_id: str
    user_id: str
    role: str
    content: str
    timestamp: int

class StorageService:
    """Unified storage service with integrated cache invalidation."""

    def __init__(self, db_service: DatabaseService, secret_provider: SecretProvider, cache_service: Optional[CacheService] = None):
        super().__init__()
        self.db = db_service
        self.cache_service = cache_service
        self.db_encryption_key = secret_provider.get("DB_ENCRYPTION_KEY")
        if not self.db_encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY not found for StorageService.")

    def _invalidate_cache_sync(self, key: str):
        if self.cache_service:
            self.cache_service.delete_sync(key)

    def create_room(self, room_id: str, name: str, owner_id: str, room_type: RoomType, parent_id: Optional[str] = None) -> Room:
        created_at = int(time.time())
        query = "INSERT INTO rooms (room_id, name, owner_id, type, parent_id, created_at, updated_at, message_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        params = (room_id, name, owner_id, room_type, parent_id, created_at, created_at, 0)
        self.db.execute_update(query, params)
        self._invalidate_cache_sync(f"rooms:{owner_id}")
        return Room(room_id=room_id, name=name, owner_id=owner_id, type=room_type, parent_id=parent_id, created_at=created_at, updated_at=created_at, message_count=0)

    def get_room(self, room_id: str) -> Optional[Room]:
        query = "SELECT * FROM rooms WHERE room_id = %s"
        result: List[RoomRow] = self.db.execute_query(query, (room_id,))
        return Room(**result[0]) if result else None

    def delete_room(self, room_id: str, owner_id: str) -> bool:
        rows_affected = self.db.execute_update("DELETE FROM rooms WHERE room_id = %s", (room_id,))
        if rows_affected > 0:
            self._invalidate_cache_sync(f"rooms:{owner_id}")
        return rows_affected > 0

    def get_rooms_by_owner(self, owner_id: str) -> List[Room]:
        results: List[RoomRow] = self.db.execute_query("SELECT * FROM rooms WHERE owner_id = %s", (owner_id,))
        return [Room(**row) for row in results]

    def update_room_name(self, room_id: str, new_name: str, owner_id: str) -> bool:
        rows_affected = self.db.execute_update("UPDATE rooms SET name = %s, updated_at = %s WHERE room_id = %s", (new_name, int(time.time()), room_id))
        if rows_affected > 0:
            self._invalidate_cache_sync(f"rooms:{owner_id}")
        return rows_affected > 0

    def save_message(self, message: Message) -> None:
        query = "INSERT INTO messages (message_id, room_id, user_id, role, content, content_searchable, timestamp, embedding) VALUES (%s, %s, %s, %s, pgp_sym_encrypt(%s, %s), %s, %s, %s)"
        params = (message.message_id, message.room_id, message.user_id, message.role, message.content, self.db_encryption_key, message.content, message.timestamp, None)
        self.db.execute_update(query, params)
        update_query = "UPDATE rooms SET message_count = message_count + 1, updated_at = %s WHERE room_id = %s"
        self.db.execute_update(update_query, (int(time.time()), message.room_id))

    def get_messages(self, room_id: str) -> List[Message]:
        query = "SELECT message_id, room_id, user_id, role, pgp_sym_decrypt(content, %s) as content, timestamp FROM messages WHERE room_id = %s ORDER BY timestamp ASC"
        params = (self.db_encryption_key, room_id)
        results: List[MessageRow] = self.db.execute_query(query, params)
        return [Message(**row) for row in results]

    def save_review_meta(self, review_meta: ReviewMeta) -> None:
        query = "INSERT INTO reviews (review_id, room_id, topic, instruction, status, total_rounds, current_round, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        params = (review_meta.review_id, review_meta.room_id, review_meta.topic, review_meta.instruction, review_meta.status, review_meta.total_rounds, review_meta.current_round, review_meta.created_at)
        self.db.execute_update(query, params)
        self._invalidate_cache_sync(f"reviews:room:{review_meta.room_id}")

    def get_review_meta(self, review_id: str) -> Optional[ReviewMeta]:
        query = "SELECT * FROM reviews WHERE review_id = %s"
        result = self.db.execute_query(query, (review_id,))
        return ReviewMeta(**result[0]) if result else None

    def get_reviews_by_room(self, room_id: str) -> List[ReviewMeta]:
        query = "SELECT * FROM reviews WHERE room_id = %s ORDER BY created_at DESC"
        results = self.db.execute_query(query, (room_id,))
        return [ReviewMeta(**row) for row in results]

    def update_review(self, review_id: str, review_data: Dict[str, Any]) -> None:
        ALLOWED_FIELDS = {'status', 'current_round', 'completed_at', 'final_report'}
        safe_data = {k: v for k, v in review_data.items() if k in ALLOWED_FIELDS}
        if not safe_data:
            return
        set_clause = ", ".join([f"{key} = %s" for key in safe_data.keys()])
        query = f"UPDATE reviews SET {set_clause} WHERE review_id = %s"
        params = list(safe_data.values()) + [review_id]
        self.db.execute_update(query, tuple(params))

        review = self.get_review_meta(review_id)
        if review:
             self._invalidate_cache_sync(f"reviews:room:{review.room_id}")
        self._invalidate_cache_sync(f"review:meta:{review_id}")
        if 'final_report' in safe_data:
            self._invalidate_cache_sync(f"review:report:{review_id}")

    def save_final_report(self, review_id: str, report_data: Dict[str, Any]) -> None:
        query = "UPDATE reviews SET final_report = %s, completed_at = %s, status = %s WHERE review_id = %s"
        params = (json.dumps(report_data), int(time.time()), "completed", review_id)
        self.db.execute_update(query, params)

        review = self.get_review_meta(review_id)
        if review:
             self._invalidate_cache_sync(f"reviews:room:{review.room_id}")
        self._invalidate_cache_sync(f"review:meta:{review_id}")
        self._invalidate_cache_sync(f"review:report:{review_id}")

    def get_final_report(self, review_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT final_report FROM reviews WHERE review_id = %s"
        result = self.db.execute_query(query, (review_id,))
        return result[0]["final_report"] if result and result[0].get("final_report") else None

    # ... (other methods remain for now)
    def save_panel_report(self, review_id: str, round_num: int, persona: str, report: PanelReport) -> None:
        query = "INSERT INTO panel_reports (review_id, round_num, persona, report_data) VALUES (%s, %s, %s, %s) ON CONFLICT (review_id, round_num, persona) DO UPDATE SET report_data = EXCLUDED.report_data;"
        self.db.execute_update(query, (review_id, round_num, persona, report.model_dump_json()))

    def get_consolidated_report(self, review_id: str, round_num: int) -> Optional[ConsolidatedReport]:
        query = "SELECT report_data FROM consolidated_reports WHERE review_id = %s AND round_num = %s"
        result = self.db.execute_query(query, (review_id, round_num))
        return ConsolidatedReport.model_validate(result[0]["report_data"]) if result and result[0].get("report_data") else None

    def log_review_event(self, event_data: Dict[str, Any]) -> None:
        query = "INSERT INTO review_events (review_id, ts, type, round, actor, content) VALUES (%s, %s, %s, %s, %s, %s)"
        params = (event_data.get("review_id"), event_data.get("ts"), event_data.get("type"), event_data.get("round"), event_data.get("actor"), event_data.get("content"))
        self.db.execute_update(query, params)

    def get_review_events(self, review_id: str, since: Optional[int] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM review_events WHERE review_id = %s " + ("AND ts > %s " if since else "") + "ORDER BY ts ASC"
        params = (review_id, since) if since else (review_id,)
        return self.db.execute_query(query, params)

    def save_review_metrics(self, metrics: ReviewMetrics) -> None:
        query = "INSERT INTO review_metrics (review_id, total_duration_seconds, total_tokens_used, total_cost_usd, round_metrics, created_at) VALUES (%s, %s, %s, %s, %s, %s)"
        params = (metrics.review_id, metrics.total_duration_seconds, metrics.total_tokens_used, metrics.total_cost_usd, json.dumps(metrics.round_metrics), metrics.created_at)
        self.db.execute_update(query, params)

    def get_all_review_metrics(self, limit: int, since: Optional[int] = None) -> List[ReviewMetrics]:
        query = "SELECT * FROM review_metrics " + ("WHERE created_at > %s " if since else "") + "ORDER BY created_at DESC LIMIT %s"
        params = (since, limit) if since else (limit,)
        results = self.db.execute_query(query, params)
        return [ReviewMetrics(**row) for row in results]
