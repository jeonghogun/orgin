"""
Storage Service - Unified interface for data persistence
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional, Literal, TypedDict, Final
from collections import defaultdict

from app.models.schemas import (
    Room,
    Message,
    ReviewMeta,
    PanelReport,
    ConsolidatedReport,
    ReviewMetrics,
)
from app.services.database_service import DatabaseService, get_database_service

logger = logging.getLogger(__name__)


# TypedDicts for raw database rows
class RoomRow(TypedDict):
    room_id: str
    name: str
    owner_id: str
    type: Literal["main", "sub", "review"]
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


# In-memory storage for room-specific data
_room_memory: Dict[str, Dict[str, str]] = defaultdict(dict)


from app.core.secrets import SecretProvider

class StorageService:
    """Unified storage service for file system and Firebase"""

    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        self.db: DatabaseService = get_database_service()
        self.db_encryption_key = secret_provider.get("DB_ENCRYPTION_KEY")
        if not self.db_encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY not found for StorageService.")

    # Memory functions for room-specific data
    async def memory_set(self, room_id: str, key: str, value: str) -> None:
        """Set a value in room memory"""
        _room_memory[room_id][key] = value
        logger.info(f"Memory set: {room_id}.{key} = {value}")

    async def memory_get(self, room_id: str, key: str) -> Optional[str]:
        """Get a value from room memory"""
        value = _room_memory[room_id].get(key)
        logger.info(f"Memory get: {room_id}.{key} = {value}")
        return value

    async def memory_clear(self, room_id: str) -> None:
        """Clear all memory for a room"""
        if room_id in _room_memory:
            del _room_memory[room_id]
            logger.info(f"Memory cleared for room: {room_id}")

    # Room operations
    async def create_room(
        self,
        room_id: str,
        name: str,
        owner_id: str,
        room_type: Literal["main", "sub", "review"],
        parent_id: Optional[str] = None,
    ) -> Room:
        """Create a new room in the database"""
        created_at = int(time.time())
        updated_at = created_at
        message_count = 0

        query = """
            INSERT INTO rooms (room_id, name, owner_id, type, parent_id, created_at, updated_at, message_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            room_id,
            name,
            owner_id,
            room_type,
            parent_id,
            created_at,
            updated_at,
            message_count,
        )

        self.db.execute_update(query, params)

        return Room(
            room_id=room_id,
            name=name,
            owner_id=owner_id,
            type=room_type,
            parent_id=parent_id,
            created_at=created_at,
            updated_at=updated_at,
            message_count=message_count,
        )

    async def get_room(self, room_id: str) -> Optional[Room]:
        """Get room by ID from the database"""
        query = "SELECT * FROM rooms WHERE room_id = %s"
        params = (room_id,)
        result: List[RoomRow] = self.db.execute_query(query, params) # type: ignore

        if not result:
            return None

        return Room(**result[0])

    async def delete_room(self, room_id: str) -> bool:
        """Delete a room and its associated data from the database."""
        query = "DELETE FROM rooms WHERE room_id = %s"
        params = (room_id,)
        rows_affected = self.db.execute_update(query, params)
        return rows_affected > 0

    async def get_rooms_by_owner(self, owner_id: str) -> List[Room]:
        """Get all rooms for a given owner from the database."""
        query = "SELECT * FROM rooms WHERE owner_id = %s"
        params = (owner_id,)
        results: List[RoomRow] = self.db.execute_query(query, params) # type: ignore
        return [Room(**row) for row in results]

    async def get_all_rooms(self) -> List[Room]:
        """Get all rooms in the system, e.g., for batch processing."""
        query = "SELECT * FROM rooms"
        results: List[RoomRow] = self.db.execute_query(query) # type: ignore
        return [Room(**row) for row in results]

    async def save_message(self, message: Message) -> None:
        """Save an encrypted message to the database."""
        embedding = None # TODO: Add embedding generation
        query = """
            INSERT INTO messages (message_id, room_id, user_id, role, content, timestamp, embedding)
            VALUES (%s, %s, %s, %s, pgp_sym_encrypt(%s, %s), %s, %s)
        """
        params = (
            message.message_id, message.room_id, message.user_id, message.role,
            message.content, self.db_encryption_key, message.timestamp, embedding
        )
        self.db.execute_update(query, params)

    async def get_messages(self, room_id: str) -> List[Message]:
        """Get and decrypt all messages for a room from the database."""
        query = """
            SELECT message_id, room_id, user_id, role,
                   pgp_sym_decrypt(content, %s) as content,
                   timestamp
            FROM messages
            WHERE room_id = %s
            ORDER BY timestamp ASC
        """
        params = (self.db_encryption_key, room_id)
        results: List[MessageRow] = self.db.execute_query(query, params)
        return [Message(**row) for row in results]

    # Review operations
    async def save_review_meta(self, review_meta: ReviewMeta) -> None:
        """Save review metadata to the database."""
        query = """
            INSERT INTO reviews (review_id, room_id, topic, instruction, status, total_rounds, current_round, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            review_meta.review_id,
            review_meta.room_id,
            review_meta.topic,
            review_meta.instruction,
            review_meta.status,
            review_meta.total_rounds,
            review_meta.current_round,
            review_meta.created_at,
        )
        self.db.execute_update(query, params)

    async def get_review_meta(self, review_id: str) -> Optional[ReviewMeta]:
        """Get review by ID from the database"""
        query = "SELECT * FROM reviews WHERE review_id = %s"
        params = (review_id,)
        result = self.db.execute_query(query, params)

        if not result:
            return None

        return ReviewMeta(**result[0])

    async def get_reviews_by_room(self, room_id: str) -> List[ReviewMeta]:
        """Get all reviews for a given room from the database."""
        query = "SELECT * FROM reviews WHERE room_id = %s ORDER BY created_at DESC"
        params = (room_id,)
        results = self.db.execute_query(query, params)
        return [ReviewMeta(**row) for row in results]

    async def get_full_reviews_by_room(self, room_id: str) -> List[ReviewFull]:
        """Get all reviews for a given room, including the final_report."""
        query = "SELECT * FROM reviews WHERE room_id = %s ORDER BY created_at DESC"
        params = (room_id,)
        results = self.db.execute_query(query, params)
        return [ReviewFull(**row) for row in results]

    async def update_review(self, review_id: str, review_data: Dict[str, Any]) -> None:
        """Update review metadata in the database."""
        # Dynamically build the SET part of the query
        set_clause = ", ".join([f"{key} = %s" for key in review_data.keys()])
        query = f"UPDATE reviews SET {set_clause} WHERE review_id = %s"

        params = list(review_data.values()) + [review_id]

        self.db.execute_update(query, tuple(params))

    async def save_panel_report(
        self, review_id: str, round_num: int, persona: str, report: PanelReport
    ) -> None:
        """Save panel report to the database."""
        query = """
            INSERT INTO panel_reports (review_id, round_num, persona, report_data)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (review_id, round_num, persona) DO UPDATE SET
                report_data = EXCLUDED.report_data;
        """
        report_json = report.model_dump_json()
        params = (review_id, round_num, persona, report_json)
        self.db.execute_update(query, params)

    async def save_consolidated_report(
        self, review_id: str, round_num: int, report: ConsolidatedReport
    ) -> None:
        """Save consolidated report to the database."""
        query = """
            INSERT INTO consolidated_reports (review_id, round_num, report_data)
            VALUES (%s, %s, %s)
            ON CONFLICT (review_id, round_num) DO UPDATE SET
                report_data = EXCLUDED.report_data;
        """
        report_json = report.model_dump_json()
        params = (review_id, round_num, report_json)
        self.db.execute_update(query, params)

    async def get_consolidated_report(
        self, review_id: str, round_num: int
    ) -> Optional[ConsolidatedReport]:
        """Get consolidated report by ID and round number"""
        query = "SELECT report_data FROM consolidated_reports WHERE review_id = %s AND round_num = %s"
        params = (review_id, round_num)
        result = self.db.execute_query(query, params)
        if result and result[0].get("report_data"):
            return ConsolidatedReport.model_validate(result[0]["report_data"])
        return None

    async def save_final_report(
        self, review_id: str, report_data: Dict[str, Any]
    ) -> None:
        """Save final report to the database."""
        query = "UPDATE reviews SET final_report = %s, completed_at = %s, status = %s WHERE review_id = %s"
        params = (json.dumps(report_data), int(time.time()), "completed", review_id)
        self.db.execute_update(query, params)

    async def get_final_report(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Get final report from the database"""
        query = "SELECT final_report FROM reviews WHERE review_id = %s"
        params = (review_id,)
        result = self.db.execute_query(query, params)
        if result and result[0]["final_report"]:
            return result[0]["final_report"]
        return None

    async def log_review_event(self, event_data: Dict[str, Any]) -> None:
        """Log review event to the database."""
        query = """
            INSERT INTO review_events (review_id, ts, type, round, actor, content)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            event_data.get("review_id"),
            event_data.get("ts"),
            event_data.get("type"),
            event_data.get("round"),
            event_data.get("actor"),
            event_data.get("content"),
        )
        self.db.execute_update(query, params)

    async def get_review_events(
        self, review_id: str, since: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get review events from the database."""
        if since:
            query = "SELECT * FROM review_events WHERE review_id = %s AND ts > %s ORDER BY ts ASC"
            params = (review_id, since)
        else:
            query = "SELECT * FROM review_events WHERE review_id = %s ORDER BY ts ASC"
            params = (review_id,)

        return self.db.execute_query(query, params)

    async def save_review_metrics(self, metrics: ReviewMetrics) -> None:
        """Save review metrics to the database."""
        query = """
            INSERT INTO review_metrics (review_id, total_duration_seconds, total_tokens_used, total_cost_usd, round_metrics, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            metrics.review_id,
            metrics.total_duration_seconds,
            metrics.total_tokens_used,
            metrics.total_cost_usd,
            json.dumps(metrics.round_metrics),
            metrics.created_at,
        )
        self.db.execute_update(query, params)

    async def get_all_review_metrics(
        self, limit: int, since: Optional[int] = None
    ) -> List[ReviewMetrics]:
        """Get all review metrics, with optional filters."""
        if since:
            query = "SELECT * FROM review_metrics WHERE created_at > %s ORDER BY created_at DESC LIMIT %s"
            params = (since, limit)
        else:
            query = "SELECT * FROM review_metrics ORDER BY created_at DESC LIMIT %s"
            params = (limit,)

        results = self.db.execute_query(query, params)
        return [ReviewMetrics(**row) for row in results]


# Global storage service instance
storage_service: Final = StorageService()
