"""Storage Service - Unified interface for data persistence."""

import json
import time
import logging
from typing import Dict, Any, List, Optional, Literal, TypedDict, Final, cast

from app.models.enums import RoomType
from app.models.schemas import (
    Room,
    Message,
    ReviewMeta,
    ReviewFull,
    PanelReport,
    ConsolidatedReport,
    ReviewMetrics,
)
from app.services.database_service import DatabaseService, get_database_service
from app.utils.helpers import get_current_timestamp

logger = logging.getLogger(__name__)


# TypedDicts for raw database rows
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


from app.core.secrets import SecretProvider, env_secrets_provider


class StorageService:
    """Unified storage service for file system and Firebase"""

    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        self.db: DatabaseService = get_database_service()
        self.db_encryption_key = secret_provider.get("DB_ENCRYPTION_KEY")
        if not self.db_encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY not found for StorageService.")

    # Room operations
    def create_room(
        self,
        room_id: str,
        name: str,
        owner_id: str,
        room_type: RoomType,
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

    def get_room(self, room_id: str) -> Optional[Room]:
        """Get room by ID from the database"""
        query = "SELECT * FROM rooms WHERE room_id = %s"
        params = (room_id,)
        result: List[RoomRow] = self.db.execute_query(query, params) # type: ignore

        if not result:
            return None

        return Room(**result[0])

    def delete_room(self, room_id: str) -> bool:
        """Delete a room and its associated data from the database."""

        cleanup_statements = [
            ("DELETE FROM conversation_messages WHERE thread_id IN (SELECT id FROM conversation_threads WHERE sub_room_id = %s)", (room_id,)),
            ("DELETE FROM conversation_threads WHERE sub_room_id = %s", (room_id,)),
            ("DELETE FROM messages WHERE room_id = %s", (room_id,)),
            ("DELETE FROM memories WHERE room_id = %s", (room_id,)),
            ("DELETE FROM reviews WHERE room_id = %s", (room_id,)),
        ]

        with self.db.transaction(query_type="delete_room") as cur:
            for statement, params in cleanup_statements:
                cur.execute(statement, params)

            cur.execute("DELETE FROM rooms WHERE room_id = %s", (room_id,))
            rows_affected = cur.rowcount

        return rows_affected > 0

    def get_rooms_by_owner(self, owner_id: str) -> List[Room]:
        """Get all rooms for a given owner from the database."""
        query = "SELECT * FROM rooms WHERE owner_id = %s"
        params = (owner_id,)
        results: List[RoomRow] = self.db.execute_query(query, params) # type: ignore
        return [Room(**row) for row in results]

    def get_all_rooms(self) -> List[Room]:
        """Get all rooms in the system, e.g., for batch processing."""
        query = "SELECT * FROM rooms"
        results: List[RoomRow] = self.db.execute_query(query) # type: ignore
        return [Room(**row) for row in results]

    def update_room_name(self, room_id: str, new_name: str) -> bool:
        """Updates the name of a specific room."""
        query = "UPDATE rooms SET name = %s, updated_at = %s WHERE room_id = %s"
        params = (new_name, int(time.time()), room_id)
        rows_affected = self.db.execute_update(query, params)
        return rows_affected > 0

    def add_message_version(self, message: Message) -> None:
        """Adds an old version of a message to the versioning table."""
        query = """
            INSERT INTO message_versions (message_id, content, role)
            VALUES (%s, %s, %s)
        """
        # Note: We save the raw (potentially encrypted) content here
        params = (message.message_id, message.content, message.role)
        self.db.execute_update(query, params)

    def get_message_versions(self, message_id: str) -> List[Dict[str, Any]]:
        """Gets all historical versions for a given message."""
        query = """
            SELECT version_id as id, message_id, content, role, created_at
            FROM message_versions
            WHERE message_id = %s
            ORDER BY created_at ASC
        """
        params = (message_id,)
        return self.db.execute_query(query, params)

    def update_message_content(self, message_id: str, new_content: str, new_content_searchable: str) -> bool:
        """Updates the content of an existing message."""
        query = """
            UPDATE messages
            SET content = pgp_sym_encrypt(%s, %s),
                content_searchable = %s,
                timestamp = %s
            WHERE message_id = %s
        """
        params = (new_content, self.db_encryption_key, new_content_searchable, get_current_timestamp(), message_id)
        rows_affected = self.db.execute_update(query, params)
        return rows_affected > 0

    def save_message(self, message: Message) -> None:
        """Save an encrypted message, update room stats, and dispatch embedding task."""
        from app.tasks.embedding_tasks import generate_embedding_for_record

        insert_query = """
            INSERT INTO messages (message_id, room_id, user_id, role, content, content_searchable, timestamp)
            VALUES (%s, %s, %s, %s, pgp_sym_encrypt(%s, %s), %s, %s)
        """
        insert_params = (
            message.message_id, message.room_id, message.user_id, message.role,
            message.content, self.db_encryption_key, message.content, message.timestamp
        )

        update_query = "UPDATE rooms SET message_count = message_count + 1, updated_at = %s WHERE room_id = %s"
        update_params = (int(time.time()), message.room_id)

        try:
            with self.db.transaction(query_type="write_message") as cur:
                cur.execute(insert_query, insert_params)
                cur.execute(update_query, update_params)

            # Dispatch the embedding task after the transaction is successfully committed.
            # Only generate embeddings for user messages to save costs/resources.
            if message.role == "user":
                try:
                    generate_embedding_for_record.delay(
                        record_id=message.message_id,
                        table_name="messages",
                        text_content=message.content
                    )
                except Exception as celery_error:
                    logger.warning(f"Failed to dispatch embedding task for message {message.message_id}: {celery_error}")
                    # Continue without embedding generation
        except Exception as e:
            logger.error(f"Transaction failed for save_message on room {message.room_id}: {e}", exc_info=True)
            # Re-raise the exception to allow higher-level error handling if needed
            raise

    def get_message(self, message_id: str) -> Optional[Message]:
        """Get a single message by its ID."""
        try:
            query = """
                SELECT message_id, room_id, user_id, role,
                       pgp_sym_decrypt(content, %s) as content,
                       timestamp
                FROM messages
                WHERE message_id = %s
            """
            params = (self.db_encryption_key, message_id)
            results: List[MessageRow] = self.db.execute_query(query, params)
            if not results:
                return None
            return Message(**results[0])
        except Exception as e:
            logger.warning(f"Decryption failed for message {message_id}: {e}")
            query = "SELECT message_id, room_id, user_id, role, content_searchable as content, timestamp FROM messages WHERE message_id = %s"
            params = (message_id,)
            results: List[MessageRow] = self.db.execute_query(query, params)
            if not results:
                return None
            return Message(**results[0])


    def get_messages(self, room_id: str) -> List[Message]:
        """Get and decrypt all messages for a room from the database."""
        # First try to get messages with decryption
        try:
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
        except Exception as e:
            logger.warning(f"Decryption failed for room {room_id}: {e}")
            # If decryption fails, try to get content_searchable instead
            query = """
                SELECT message_id, room_id, user_id, role,
                       content_searchable as content,
                       timestamp
                FROM messages
                WHERE room_id = %s
                ORDER BY timestamp ASC
            """
            params = (room_id,)
            results: List[MessageRow] = self.db.execute_query(query, params)
            return [Message(**row) for row in results]

    # Review operations
    def save_review_meta(self, review_meta: ReviewMeta) -> None:
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

    def get_review_meta(self, review_id: str) -> Optional[ReviewMeta]:
        """Get review by ID from the database"""
        # Select only the columns that exist in the ReviewMeta model to avoid schema drift issues.
        query = """
            SELECT
                review_id,
                room_id,
                topic,
                instruction,
                status,
                total_rounds,
                current_round,
                created_at,
                completed_at
            FROM reviews
            WHERE review_id = %s
        """
        params = (review_id,)
        result = self.db.execute_query(query, params)

        if not result:
            return None

        # The DB doesn't have 'started_at' or 'failed_panels'. Pydantic will use defaults.
        return ReviewMeta(**result[0])

    def get_review_meta_by_room_id(self, room_id: str) -> Optional[ReviewMeta]:
        """Get the latest review for a given room_id from the database."""
        query = """
            SELECT
                review_id,
                room_id,
                topic,
                instruction,
                status,
                total_rounds,
                current_round,
                created_at,
                completed_at
            FROM reviews
            WHERE room_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """
        params = (room_id,)
        result = self.db.execute_query(query, params)

        if not result:
            return None

        return ReviewMeta(**result[0])

    def get_reviews_by_room(self, room_id: str) -> List[ReviewMeta]:
        """Get all reviews for a given room from the database."""
        query = "SELECT * FROM reviews WHERE room_id = %s ORDER BY created_at DESC"
        params = (room_id,)
        results = self.db.execute_query(query, params)
        return [ReviewMeta(**row) for row in results]

    def get_full_reviews_by_room(self, room_id: str) -> List[ReviewFull]:
        """Get all reviews for a given room, including the final_report."""
        query = """
            SELECT r.*
            FROM reviews r
            LEFT JOIN rooms rm ON r.room_id = rm.room_id
            WHERE r.room_id = %s OR rm.parent_id = %s
            ORDER BY r.created_at DESC
        """
        params = (room_id, room_id)
        results = self.db.execute_query(query, params)
        return [ReviewFull(**row) for row in results]

    def update_review(self, review_id: str, review_data: Dict[str, Any]) -> None:
        """Update review metadata in the database safely."""
        # Whitelist of fields that are allowed to be updated.
        ALLOWED_FIELDS = {'status', 'current_round', 'completed_at', 'final_report'}

        # Filter the incoming data to only include allowed fields.
        safe_data = {k: v for k, v in review_data.items() if k in ALLOWED_FIELDS}

        if not safe_data:
            logger.warning(f"Update review called for {review_id} with no valid fields: {review_data}")
            return

        # Dynamically build the SET part of the query from safe data
        set_clause = ", ".join([f"{key} = %s" for key in safe_data.keys()])
        query = f"UPDATE reviews SET {set_clause} WHERE review_id = %s"

        params = list(safe_data.values()) + [review_id]

        self.db.execute_update(query, tuple(params))

    def save_panel_report(
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

    def save_consolidated_report(
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

    def get_consolidated_report(
        self, review_id: str, round_num: int
    ) -> Optional[ConsolidatedReport]:
        """Get consolidated report by ID and round number"""
        query = "SELECT report_data FROM consolidated_reports WHERE review_id = %s AND round_num = %s"
        params = (review_id, round_num)
        result = self.db.execute_query(query, params)
        if result and result[0].get("report_data"):
            return ConsolidatedReport.model_validate(result[0]["report_data"])
        return None

    def save_final_report(
        self, review_id: str, report_data: Dict[str, Any]
    ) -> None:
        """Save final report to the database."""
        query = "UPDATE reviews SET final_report = %s, completed_at = %s, status = %s WHERE review_id = %s"
        params = (json.dumps(report_data), int(time.time()), "completed", review_id)
        self.db.execute_update(query, params)

    def get_final_report(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Get final report from the database"""
        query = "SELECT final_report FROM reviews WHERE review_id = %s"
        params = (review_id,)
        result = self.db.execute_query(query, params)
        if result and result[0]["final_report"]:
            return result[0]["final_report"]
        return None

    def log_review_event(self, event_data: Dict[str, Any]) -> None:
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

    def get_review_events(
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

    def save_review_metrics(self, metrics: ReviewMetrics) -> None:
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

    def get_all_review_metrics(
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


    def save_embedding(self, table_name: str, record_id: str, embedding: List[float]) -> None:
        """
        Saves a vector embedding for a specific record in a given table.
        """
        # A mapping of table names to their primary key column names
        # This is a security measure to prevent arbitrary table updates.
        allowed_tables = {
            "messages": "message_id",
            "attachment_chunks": "id",
        }

        if table_name not in allowed_tables:
            logger.error(f"Attempted to save embedding to an unsupported table: {table_name}")
            raise ValueError(f"Table '{table_name}' is not supported for embedding updates.")

        pk_column = allowed_tables[table_name]

        # Use f-string for table and column names as they are controlled by the allowlist,
        # and use parameterization for the actual values to prevent SQL injection.
        query = f"UPDATE {table_name} SET embedding = %s WHERE {pk_column} = %s"
        params = (embedding, record_id)

        self.db.execute_update(query, params)


_storage_service_instance: Optional[StorageService] = None


def _get_or_create_storage_service() -> StorageService:
    """Create the storage service lazily to avoid early database lookups."""

    global _storage_service_instance
    if _storage_service_instance is None:
        _storage_service_instance = StorageService(env_secrets_provider)
    return _storage_service_instance


class _StorageServiceProxy:
    """Lightweight proxy to defer instantiation until first real use."""

    def __getattr__(self, name: str):  # type: ignore[override]
        return getattr(_get_or_create_storage_service(), name)


# Export a proxy that behaves like the concrete service for callers that import
# ``storage_service`` directly (e.g. legacy routes and Celery tasks).
storage_service: Final[StorageService] = cast(StorageService, _StorageServiceProxy())


def get_storage_service() -> StorageService:
    """Return the lazily-instantiated storage service instance."""

    return _get_or_create_storage_service()
