"""Service layer for handling conversation logic backed by raw SQL."""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import redis
from psycopg2.extras import Json

from app.config.settings import settings
from app.models.conversation_schemas import (
    Attachment,
    ConversationMessage,
    ConversationThread,
    ConversationThreadCreate,
)
from app.services.database_service import DatabaseService, get_database_service
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(self):
        self.db: DatabaseService = get_database_service()
        self.redis_client = redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None

    def increment_token_usage(self, user_id: str, token_count: int) -> int:
        """Increments a user's token usage for the day in Redis."""
        if not self.redis_client:
            logger.info(f"Token usage tracking skipped (Redis not available)")
            return 0
        today = time.strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}"

        new_usage = self.redis_client.incrby(key, token_count)
        # Set expiry to 24 hours on first increment
        if new_usage == token_count:
            self.redis_client.expire(key, 86400) # 24 hours

        return new_usage

    def get_today_usage(self, user_id: str) -> int:
        """Gets a user's token usage for the day from Redis."""
        if not self.redis_client:
            logger.info(f"Token usage tracking skipped (Redis not available)")
            return 0
        today = time.strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}"
        usage = self.redis_client.get(key)
        return int(usage) if usage else 0

    def create_thread(self, room_id: str, user_id: str, thread_data: ConversationThreadCreate) -> ConversationThread:
        thread_id = f"thr_{generate_id()}"
        insert_query = """
            INSERT INTO conversation_threads (id, sub_room_id, user_id, title, pinned, archived)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, sub_room_id, user_id, title, pinned, archived, created_at, updated_at
        """
        params = (thread_id, room_id, user_id, thread_data.title, False, False)
        rows = self.db.execute_returning(insert_query, params)
        if not rows:
            raise RuntimeError("Failed to create conversation thread")
        return self._map_thread_row(rows[0])

    async def get_threads_by_room(self, room_id: str, query: Optional[str] = None, pinned: Optional[bool] = None, archived: Optional[bool] = None) -> List[ConversationThread]:
        sql_query = "SELECT id, sub_room_id, user_id, title, pinned, archived, created_at, updated_at FROM conversation_threads WHERE sub_room_id = %s"
        params: List[Any] = [room_id]
        if query:
            sql_query += " AND title ILIKE %s"
            params.append(f"%{query}%")
        if pinned is not None:
            sql_query += " AND pinned = %s"
            params.append(pinned)
        if archived is not None:
            sql_query += " AND archived = %s"
            params.append(archived)
        sql_query += " ORDER BY updated_at DESC"
        results = await asyncio.to_thread(self.db.execute_query, sql_query, tuple(params))
        return [self._map_thread_row(row) for row in results]

    def create_message(self, thread_id: str, role: str, content: str, status: str = "draft", model: Optional[str] = None, meta: Optional[Dict[str, Any]] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        message_id = f"msg_{generate_id()}"
        meta_payload: Dict[str, Any] = meta.copy() if isinstance(meta, dict) else {}
        meta_payload.setdefault("userId", user_id)
        insert_query = """
            INSERT INTO conversation_messages (id, thread_id, role, content, model, status, meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, thread_id, role, content, model, status, created_at, meta
        """
        params = (
            message_id,
            thread_id,
            role,
            content,
            model,
            status,
            Json(meta_payload) if meta_payload else None,
        )
        rows = self.db.execute_returning(insert_query, params)
        if not rows:
            raise RuntimeError("Failed to create conversation message")

        self.db.execute_update("UPDATE conversation_threads SET updated_at = NOW() WHERE id = %s", (thread_id,))

        db_row = rows[0]
        normalized_meta = self._deserialize_meta(db_row.get("meta"))
        created_at = self._normalize_timestamp(db_row.get("created_at"))
        return {
            "id": db_row["id"],
            "thread_id": db_row["thread_id"],
            "role": db_row["role"],
            "content": db_row["content"],
            "status": db_row["status"],
            "model": db_row.get("model"),
            "meta": normalized_meta,
            "created_at": created_at,
        }

    def update_message(self, message_id: str, content: str, status: str, meta: Dict[str, Any]) -> None:
        meta_payload = Json(meta) if meta else None
        query = "UPDATE conversation_messages SET content = %s, status = %s, meta = %s WHERE id = %s"
        params = (content, status, meta_payload, message_id)
        self.db.execute_update(query, params)

    def get_messages_by_thread(self, thread_id: str, cursor: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql_query = "SELECT id, thread_id, role, content, model, status, created_at, meta FROM conversation_messages WHERE thread_id = %s"
        params: List[Any] = [thread_id]
        if cursor:
            sql_query += " AND created_at < %s"
            params.append(self._cursor_to_datetime(cursor))
        sql_query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        results = self.db.execute_query(sql_query, tuple(params))
        return [self._map_message_row(row) for row in results]

    async def get_all_messages_by_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        query = "SELECT id, thread_id, role, content, model, status, created_at, meta FROM conversation_messages WHERE thread_id = %s ORDER BY created_at ASC"
        params = (thread_id,)
        results = await asyncio.to_thread(self.db.execute_query, query, params)
        return [self._map_message_row(row) for row in results]

    def get_message_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT id, thread_id, role, content, model, status, created_at, meta FROM conversation_messages WHERE id = %s"
        params = (message_id,)
        results = self.db.execute_query(query, params)
        if not results:
            return None
        return self._map_message_row(results[0])

    def create_new_message_version(self, original_message_id: str, new_content: str) -> Optional[Dict[str, Any]]:
        """Creates a new version of a user message, linking it to the original."""
        original_message = self.get_message_by_id(original_message_id)
        if not original_message or original_message.get("role") != "user":
            return None

        new_meta = original_message.get("meta", {}) or {}
        new_meta["parentId"] = original_message_id

        # Create a new message with the new content and parentId
        new_message = self.create_message(
            thread_id=original_message["thread_id"],
            role="user",
            content=new_content,
            status="complete",
            meta=new_meta
        )
        return new_message

    def get_attachment_by_id(self, attachment_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT id, kind, name, mime, size, url, created_at FROM attachments WHERE id = %s"
        params = (attachment_id,)
        results = self.db.execute_query(query, params)
        return results[0] if results else None

    def create_export_job(self, thread_id: str, user_id: str, format: str) -> Dict[str, Any]:
        job_id = f"exp_{generate_id()}"
        query = """
            INSERT INTO export_jobs (id, thread_id, user_id, format)
            VALUES (%s, %s, %s, %s)
            RETURNING id, status
        """
        rows = self.db.execute_returning(query, (job_id, thread_id, user_id, format))
        if not rows:
            raise RuntimeError("Failed to create export job")
        return {"id": rows[0]["id"], "status": rows[0]["status"]}

    def get_export_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT id, thread_id, user_id, format, status, file_url, error_message, created_at, updated_at FROM export_jobs WHERE id = %s"
        params = (job_id,)
        results = self.db.execute_query(query, params)
        return results[0] if results else None

    def update_export_job_status(self, job_id: str, status: str, file_url: Optional[str] = None, error_message: Optional[str] = None):
        query = "UPDATE export_jobs SET status = %s, file_url = %s, error_message = %s, updated_at = NOW() WHERE id = %s"
        params = (status, file_url, error_message, job_id)
        self.db.execute_update(query, params)

    def get_room_hierarchy(self, thread_id: str) -> Dict[str, Optional[str]]:
        """
        Given a thread_id, finds the sub_room_id and its parent main_room_id.
        """
        thread_query = "SELECT sub_room_id FROM conversation_threads WHERE id = %s"
        thread_result = self.db.execute_query(thread_query, (thread_id,))
        if not thread_result:
            return {"current_room": None, "parent_room": None}

        room_id = thread_result[0].get("sub_room_id")
        if not room_id:
            return {"current_room": None, "parent_room": None}

        # Second, get the parent_id from the rooms table
        room_query = "SELECT parent_id FROM rooms WHERE room_id = %s"
        room_result = self.db.execute_query(room_query, (room_id,))

        parent_room_id = None
        if room_result:
            parent_room_id = room_result[0].get("parent_id")

        return {"current_room": room_id, "parent_room": parent_room_id}

    def get_message_versions(self, message_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all versions of a message by traversing the parentId chain.
        """
        versions = []
        current_id = message_id
        for _ in range(20): # Safety break to prevent infinite loops
            msg = self.get_message_by_id(current_id)
            if not msg:
                break
            versions.append(msg)
            meta = msg.get("meta")
            if meta and isinstance(meta, dict) and meta.get("parentId"):
                current_id = meta["parentId"]
            else:
                break
        return list(reversed(versions)) # Return oldest first

    def create_attachment(self, attachment_data: Dict[str, Any]) -> Attachment:
        attachment_id = f"att_{generate_id()}"
        insert_query = """
            INSERT INTO attachments (id, kind, name, mime, size, url)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, kind, name, mime, size, url, created_at
        """
        params = (
            attachment_id,
            attachment_data["kind"],
            attachment_data["name"],
            attachment_data["mime"],
            attachment_data["size"],
            attachment_data["url"],
        )
        rows = self.db.execute_returning(insert_query, params)
        if not rows:
            raise RuntimeError("Failed to create attachment")
        row = rows[0]
        payload = {
            "id": row["id"],
            "kind": row["kind"],
            "name": row["name"],
            "mime": row["mime"],
            "size": row["size"],
            "url": row["url"],
            "created_at": self._normalize_timestamp(row.get("created_at")),
        }
        return Attachment(**payload)

    # ----- Internal helpers -----

    def _normalize_timestamp(self, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, datetime):
            dt = value.astimezone(timezone.utc)
            return int(dt.timestamp())
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                try:
                    dt = datetime.fromisoformat(value)
                except ValueError:
                    return 0
                return int(dt.replace(tzinfo=timezone.utc if dt.tzinfo is None else dt.tzinfo).timestamp())
        return 0

    def _cursor_to_datetime(self, cursor: str) -> datetime:
        try:
            ts = int(cursor)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    def _deserialize_meta(self, meta_value: Any) -> Dict[str, Any]:
        if meta_value is None:
            return {}
        if isinstance(meta_value, dict):
            return meta_value
        if isinstance(meta_value, str):
            try:
                return json.loads(meta_value)
            except json.JSONDecodeError:
                return {}
        return {}

    def _map_thread_row(self, row: Dict[str, Any]) -> ConversationThread:
        return ConversationThread(
            id=row["id"],
            sub_room_id=row["sub_room_id"],
            user_id=row.get("user_id", ""),
            title=row["title"],
            pinned=row.get("pinned", False),
            archived=row.get("archived", False),
            created_at=self._normalize_timestamp(row.get("created_at")),
            updated_at=self._normalize_timestamp(row.get("updated_at")),
        )

    def _map_message_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        meta = self._deserialize_meta(row.get("meta"))
        if "userId" not in meta and "user_id" in row:
            meta["userId"] = row["user_id"]
        created_at = self._normalize_timestamp(row.get("created_at"))
        return {
            "id": row["id"],
            "thread_id": row["thread_id"],
            "role": row["role"],
            "content": row["content"],
            "model": row.get("model"),
            "status": row.get("status", "draft"),
            "created_at": created_at,
            "meta": meta,
        }

# Global service instance
conversation_service: "ConversationService" = None

def get_conversation_service() -> "ConversationService":
    global conversation_service
    if conversation_service is None:
        conversation_service = ConversationService()
    return conversation_service
