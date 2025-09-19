"""Repository layer for conversation-related persistence logic."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from app.models.conversation_schemas import Attachment, ConversationThread
from app.services.database_service import DatabaseService, get_database_service
from app.utils.helpers import generate_id


class ConversationRepository:
    """Encapsulates all direct database access for conversations."""

    def __init__(self, db: Optional[DatabaseService] = None) -> None:
        self.db = db or get_database_service()

    # --- Thread helpers -------------------------------------------------

    def create_thread(self, room_id: str, user_id: str, title: str) -> ConversationThread:
        thread_id = f"thr_{generate_id()}"
        query = """
            INSERT INTO conversation_threads (id, sub_room_id, user_id, title, pinned, archived)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, sub_room_id, user_id, title, pinned, archived, created_at, updated_at
        """
        rows = self.db.execute_returning(query, (thread_id, room_id, user_id, title, False, False))
        if not rows:
            raise RuntimeError("Failed to create conversation thread")
        return self._map_thread_row(rows[0])

    def touch_room(self, room_id: str) -> None:
        try:
            self.db.execute_update("UPDATE rooms SET updated_at = %s WHERE room_id = %s", (int(time.time()), room_id))
        except Exception:  # pragma: no cover - best effort only
            pass

    async def list_threads(
        self,
        room_id: str,
        query_text: Optional[str] = None,
        pinned: Optional[bool] = None,
        archived: Optional[bool] = None,
    ) -> List[ConversationThread]:
        sql = (
            "SELECT id, sub_room_id, user_id, title, pinned, archived, created_at, updated_at "
            "FROM conversation_threads WHERE sub_room_id = %s"
        )
        params: List[Any] = [room_id]
        if query_text:
            sql += " AND title ILIKE %s"
            params.append(f"%{query_text}%")
        if pinned is not None:
            sql += " AND pinned = %s"
            params.append(pinned)
        if archived is not None:
            sql += " AND archived = %s"
            params.append(archived)
        sql += " ORDER BY updated_at DESC"
        results = await asyncio.to_thread(self.db.execute_query, sql, tuple(params))
        return [self._map_thread_row(row) for row in results]

    def update_thread(
        self,
        thread_id: str,
        updates: Dict[str, Any],
    ) -> Optional[ConversationThread]:
        if not updates:
            return self.get_thread(thread_id)

        set_clauses: List[str] = []
        params: List[Any] = []

        if "title" in updates and updates["title"] is not None:
            set_clauses.append("title = %s")
            params.append(updates["title"])
        if "pinned" in updates and updates["pinned"] is not None:
            set_clauses.append("pinned = %s")
            params.append(bool(updates["pinned"]))
        if "archived" in updates and updates["archived"] is not None:
            set_clauses.append("archived = %s")
            params.append(bool(updates["archived"]))

        if not set_clauses:
            return self.get_thread(thread_id)

        set_clauses.append("updated_at = NOW()")
        sql = (
            "UPDATE conversation_threads SET "
            + ", ".join(set_clauses)
            + " WHERE id = %s RETURNING id, sub_room_id, user_id, title, pinned, archived, created_at, updated_at"
        )
        params.append(thread_id)
        rows = self.db.execute_returning(sql, tuple(params))
        if not rows:
            return None
        return self._map_thread_row(rows[0])

    def delete_thread(self, thread_id: str) -> bool:
        deleted = self.db.execute_update("DELETE FROM conversation_threads WHERE id = %s", (thread_id,))
        return deleted > 0

    def get_thread(self, thread_id: str) -> Optional[ConversationThread]:
        sql = (
            "SELECT id, sub_room_id, user_id, title, pinned, archived, created_at, updated_at "
            "FROM conversation_threads WHERE id = %s"
        )
        rows = self.db.execute_query(sql, (thread_id,))
        if not rows:
            return None
        return self._map_thread_row(rows[0])

    # --- Messages -------------------------------------------------------

    def create_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        status: str = "draft",
        model: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        user_id: str = "anonymous",
    ) -> Dict[str, Any]:
        message_id = f"msg_{generate_id()}"
        meta_payload = meta.copy() if isinstance(meta, dict) else {}
        meta_payload.setdefault("userId", user_id)
        if model and "model" not in meta_payload:
            meta_payload["model"] = model

        query = """
            INSERT INTO conversation_messages (id, thread_id, user_id, role, content, model, status, meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, thread_id, user_id, role, content, model, status, created_at, meta
        """
        rows = self.db.execute_returning(
            query,
            (
                message_id,
                thread_id,
                user_id,
                role,
                content,
                model,
                status,
                Json(meta_payload) if meta_payload else None,
            ),
        )
        if not rows:
            raise RuntimeError("Failed to create conversation message")
        self.db.execute_update("UPDATE conversation_threads SET updated_at = NOW() WHERE id = %s", (thread_id,))
        return self._map_message_row(rows[0])

    def update_message_content(self, message_id: str, content: str, status: str, meta: Dict[str, Any]) -> None:
        self.db.execute_update(
            "UPDATE conversation_messages SET content = %s, status = %s, meta = %s WHERE id = %s",
            (content, status, Json(meta) if meta else None, message_id),
        )

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        sql = (
            "SELECT id, thread_id, user_id, role, content, model, status, created_at, meta "
            "FROM conversation_messages WHERE id = %s"
        )
        rows = self.db.execute_query(sql, (message_id,))
        if not rows:
            return None
        return self._map_message_row(rows[0])

    def list_messages(self, thread_id: str, cursor: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql = (
            "SELECT id, thread_id, user_id, role, content, model, status, created_at, meta "
            "FROM conversation_messages WHERE thread_id = %s"
        )
        params: List[Any] = [thread_id]
        if cursor:
            sql += " AND created_at < %s"
            params.append(self._cursor_to_datetime(cursor))
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self.db.execute_query(sql, tuple(params))
        return [self._map_message_row(row) for row in rows]

    async def list_all_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        sql = (
            "SELECT id, thread_id, user_id, role, content, model, status, created_at, meta "
            "FROM conversation_messages WHERE thread_id = %s ORDER BY created_at ASC"
        )
        rows = await asyncio.to_thread(self.db.execute_query, sql, (thread_id,))
        return [self._map_message_row(row) for row in rows]

    def search_messages(
        self,
        query_text: str,
        *,
        thread_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        sql = (
            "SELECT id, thread_id, user_id, role, content, model, status, created_at, meta "
            "FROM conversation_messages WHERE content ILIKE %s"
        )
        params: List[Any] = [f"%{query_text}%"]
        if thread_id:
            sql += " AND thread_id = %s"
            params.append(thread_id)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self.db.execute_query(sql, tuple(params))
        results = [self._map_message_row(row) for row in rows]
        return {"query": query_text, "total_results": len(results), "results": results}

    # --- Attachments ----------------------------------------------------

    def create_attachment(self, data: Dict[str, Any], thread_id: Optional[str] = None) -> Attachment:
        attachment_id = f"att_{generate_id()}"
        query = """
            INSERT INTO attachments (id, thread_id, kind, name, mime, size, url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, thread_id, kind, name, mime, size, url, created_at
        """
        rows = self.db.execute_returning(
            query,
            (
                attachment_id,
                thread_id,
                data["kind"],
                data["name"],
                data["mime"],
                data["size"],
                data["url"],
            ),
        )
        if not rows:
            raise RuntimeError("Failed to create attachment")
        row = rows[0]
        payload = {
            "id": row["id"],
            "thread_id": row.get("thread_id"),
            "kind": row["kind"],
            "name": row["name"],
            "mime": row["mime"],
            "size": row["size"],
            "url": row["url"],
            "created_at": self._normalize_timestamp(row.get("created_at")),
        }
        return Attachment(**payload)

    def get_attachment(self, attachment_id: str) -> Optional[Dict[str, Any]]:
        rows = self.db.execute_query(
            "SELECT id, thread_id, kind, name, mime, size, url, created_at FROM attachments WHERE id = %s",
            (attachment_id,),
        )
        return rows[0] if rows else None

    # --- Export jobs ----------------------------------------------------

    def create_export_job(self, thread_id: str, user_id: str, export_format: str) -> Dict[str, Any]:
        job_id = f"exp_{generate_id()}"
        query = """
            INSERT INTO export_jobs (id, thread_id, user_id, format)
            VALUES (%s, %s, %s, %s)
            RETURNING id, status
        """
        rows = self.db.execute_returning(query, (job_id, thread_id, user_id, export_format))
        if not rows:
            raise RuntimeError("Failed to create export job")
        return {"id": rows[0]["id"], "status": rows[0]["status"]}

    def get_export_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        rows = self.db.execute_query(
            "SELECT id, thread_id, user_id, format, status, file_url, error_message, created_at, updated_at "
            "FROM export_jobs WHERE id = %s",
            (job_id,),
        )
        return rows[0] if rows else None

    def update_export_job(
        self,
        job_id: str,
        status: str,
        *,
        file_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self.db.execute_update(
            "UPDATE export_jobs SET status = %s, file_url = %s, error_message = %s, updated_at = NOW() WHERE id = %s",
            (status, file_url, error_message, job_id),
        )

    # --- Misc helpers ---------------------------------------------------

    def get_room_hierarchy(self, thread_id: str) -> Dict[str, Optional[str]]:
        thread_rows = self.db.execute_query(
            "SELECT sub_room_id FROM conversation_threads WHERE id = %s",
            (thread_id,),
        )
        if not thread_rows:
            return {"current_room": None, "parent_room": None}
        room_id = thread_rows[0].get("sub_room_id")
        if not room_id:
            return {"current_room": None, "parent_room": None}
        room_rows = self.db.execute_query("SELECT parent_id FROM rooms WHERE room_id = %s", (room_id,))
        parent_id = room_rows[0].get("parent_id") if room_rows else None
        return {"current_room": room_id, "parent_room": parent_id}

    def list_message_versions(self, message_id: str, max_depth: int = 20) -> List[Dict[str, Any]]:
        versions: List[Dict[str, Any]] = []
        current_id = message_id
        for _ in range(max_depth):
            message = self.get_message(current_id)
            if not message:
                break
            versions.append(message)
            meta = message.get("meta")
            if isinstance(meta, dict) and meta.get("parentId"):
                current_id = meta["parentId"]
            else:
                break
        return list(reversed(versions))

    # --- Private helpers ------------------------------------------------

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
                tz = timezone.utc if dt.tzinfo is None else dt.tzinfo
                return int(dt.astimezone(tz).timestamp())
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
            except Exception:  # pragma: no cover - defensive
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
        if "userId" not in meta and row.get("user_id"):
            meta["userId"] = row.get("user_id")
        if row.get("model") and "model" not in meta:
            meta["model"] = row.get("model")
        created_at = self._normalize_timestamp(row.get("created_at"))
        return {
            "id": row["id"],
            "thread_id": row["thread_id"],
            "user_id": row.get("user_id"),
            "role": row["role"],
            "content": row["content"],
            "model": row.get("model"),
            "status": row.get("status", "draft"),
            "created_at": created_at,
            "meta": meta,
        }


conversation_repository: Optional[ConversationRepository] = None


def get_conversation_repository() -> ConversationRepository:  # pragma: no cover - simple accessor
    global conversation_repository
    if conversation_repository is None:
        conversation_repository = ConversationRepository()
    return conversation_repository
