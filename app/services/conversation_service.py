"""
Service layer for handling conversation logic, using raw SQL pattern.
"""
import json
import logging
import time
from typing import List, Optional, Dict, Any

from app.models.conversation_schemas import ConversationThread, ConversationThreadCreate, Attachment
import redis
from app.config.settings import settings
from app.services.database_service import DatabaseService, get_database_service
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(self):
        self.db: DatabaseService = get_database_service()
        self.redis_client = redis.from_url(settings.REDIS_URL)

    def increment_token_usage(self, user_id: str, token_count: int) -> int:
        """Increments a user's token usage for the day in Redis."""
        today = time.strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}"

        new_usage = self.redis_client.incrby(key, token_count)
        # Set expiry to 24 hours on first increment
        if new_usage == token_count:
            self.redis_client.expire(key, 86400) # 24 hours

        return new_usage

    def get_today_usage(self, user_id: str) -> int:
        """Gets a user's token usage for the day from Redis."""
        today = time.strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}"
        usage = self.redis_client.get(key)
        return int(usage) if usage else 0

    def create_thread(self, sub_room_id: str, user_id: str, thread_data: ConversationThreadCreate) -> ConversationThread:
        thread_id = f"thr_{generate_id()}"
        ts = int(time.time())
        query = """
            INSERT INTO conversation_threads (id, sub_room_id, user_id, title, pinned, archived, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (thread_id, sub_room_id, user_id, thread_data.title, False, False, ts, ts)
        self.db.execute_update(query, params)
        return ConversationThread(id=thread_id, sub_room_id=sub_room_id, user_id=user_id, title=thread_data.title, pinned=False, archived=False, created_at=ts, updated_at=ts)

    def get_threads_by_subroom(self, sub_room_id: str, query: Optional[str] = None, pinned: Optional[bool] = None, archived: Optional[bool] = None) -> List[ConversationThread]:
        sql_query = "SELECT * FROM conversation_threads WHERE sub_room_id = %s"
        params: List[Any] = [sub_room_id]
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
        results = self.db.execute_query(sql_query, tuple(params))
        return [ConversationThread(**row) for row in results]

    def create_message(self, thread_id: str, role: str, content: str, status: str = "draft", model: Optional[str] = None, meta: Optional[Dict[str, Any]] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        message_id = f"msg_{generate_id()}"
        ts = int(time.time())
        meta_json = json.dumps(meta) if meta else None
        query = """
            INSERT INTO messages (message_id, room_id, user_id, role, content, content_searchable, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        params = (message_id, thread_id, user_id, role, content, content, ts)
        self.db.execute_update(query, params)
        # thread_update_query = "UPDATE conversation_threads SET updated_at = %s WHERE id = %s"
        # self.db.execute_update(thread_update_query, (ts, thread_id))
        return {"id": message_id, "thread_id": thread_id, "role": role, "content": content, "status": status, "model": model, "meta": meta, "created_at": ts}

    def update_message(self, message_id: str, content: str, status: str, meta: Dict[str, Any]) -> None:
        meta_json = json.dumps(meta)
        query = "UPDATE messages SET content = %s WHERE message_id = %s"
        params = (content, message_id)
        self.db.execute_update(query, params)

    def get_messages_by_thread(self, thread_id: str, cursor: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql_query = "SELECT * FROM messages WHERE room_id = %s"
        params: List[Any] = [thread_id]
        if cursor:
            sql_query += " AND timestamp < %s"
            params.append(int(cursor))
        sql_query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        results = self.db.execute_query(sql_query, tuple(params))
        for row in results:
            if row and row.get('meta'):
                row['meta'] = json.loads(row['meta'])
        return results

    def get_all_messages_by_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        query = "SELECT * FROM conversation_messages WHERE thread_id = %s ORDER BY created_at ASC"
        params = (thread_id,)
        results = self.db.execute_query(query, params)
        for row in results:
            if row and row.get('meta'):
                row['meta'] = json.loads(row['meta'])
        return results

    def get_message_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM messages WHERE message_id = %s"
        params = (message_id,)
        results = self.db.execute_query(query, params)
        if not results:
            return None
        row = results[0]
        if row and row.get('meta'):
            row['meta'] = json.loads(row['meta'])
        return row

    def create_new_message_version(self, original_message_id: str, new_content: str) -> Dict[str, Any]:
        """Creates a new version of a user message, linking it to the original."""
        original_message = self.get_message_by_id(original_message_id)
        if not original_message or original_message["role"] != "user":
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
        query = "SELECT * FROM attachments WHERE id = %s"
        params = (attachment_id,)
        results = self.db.execute_query(query, params)
        return results[0] if results else None

    def create_export_job(self, thread_id: str, user_id: str, format: str) -> Dict[str, Any]:
        job_id = f"exp_{generate_id()}"
        ts = int(time.time())
        query = """
            INSERT INTO export_jobs (id, thread_id, user_id, format, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'queued', %s, %s)
        """
        params = (job_id, thread_id, user_id, format, ts, ts)
        self.db.execute_update(query, params)
        return {"id": job_id, "status": "queued"}

    def get_export_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM export_jobs WHERE id = %s"
        params = (job_id,)
        results = self.db.execute_query(query, params)
        return results[0] if results else None

    def update_export_job_status(self, job_id: str, status: str, file_url: Optional[str] = None, error_message: Optional[str] = None):
        query = "UPDATE export_jobs SET status = %s, file_url = %s, error_message = %s, updated_at = %s WHERE id = %s"
        params = (status, file_url, error_message, int(time.time()), job_id)
        self.db.execute_update(query, params)

    def get_message_versions(self, message_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all versions of a message by traversing the parentId chain.
        This is a recursive query, which can be slow. Use with caution.
        """
        # This is a simplified implementation. A real one would use a recursive CTE in SQL.
        versions = []
        current_id = message_id
        for _ in range(20): # Safety break to prevent infinite loops
            msg = self.get_message_by_id(current_id)
            if not msg:
                break
            versions.append(msg)
            if msg.get("meta") and msg["meta"].get("parentId"):
                current_id = msg["meta"]["parentId"]
            else:
                break
        return list(reversed(versions)) # Return oldest first

    def create_attachment(self, attachment_data: Dict[str, Any]) -> Attachment:
        attachment_id = f"att_{generate_id()}"
        ts = int(time.time())
        query = "INSERT INTO attachments (id, kind, name, mime, size, url, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        params = (attachment_id, attachment_data["kind"], attachment_data["name"], attachment_data["mime"], attachment_data["size"], attachment_data["url"], ts)
        self.db.execute_update(query, params)
        return Attachment(id=attachment_id, created_at=ts, **attachment_data)

# Global service instance
conversation_service: "ConversationService" = None

def get_conversation_service() -> "ConversationService":
    global conversation_service
    if conversation_service is None:
        conversation_service = ConversationService()
    return conversation_service
