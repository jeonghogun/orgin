"""
Service layer for handling conversation logic, using raw SQL pattern.
"""
import json
import logging
import time
from typing import List, Optional, Dict, Any

from app.models.conversation_schemas import ConversationThread, ConversationThreadCreate, Attachment, ConversationMessage
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

    def create_thread(self, room_id: str, user_id: str, thread_data: ConversationThreadCreate) -> ConversationThread:
        thread_id = f"thr_{generate_id()}"
        created_at = int(time.time())
        query = """
            INSERT INTO conversation_threads (thread_id, sub_room_id, title, is_pinned, is_archived, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        params = (thread_id, room_id, thread_data.title, False, False, created_at, created_at)
        self.db.execute_update(query, params)
        return ConversationThread(id=thread_id, sub_room_id=room_id, user_id=user_id, title=thread_data.title, pinned=False, archived=False, created_at=created_at, updated_at=created_at)

    def get_threads_by_room(self, room_id: str, query: Optional[str] = None, pinned: Optional[bool] = None, archived: Optional[bool] = None) -> List[ConversationThread]:
        sql_query = "SELECT * FROM conversation_threads WHERE sub_room_id = %s"
        params: List[Any] = [room_id]
        if query:
            sql_query += " AND title ILIKE %s"
            params.append(f"%{query}%")
        if pinned is not None:
            sql_query += " AND is_pinned = %s"
            params.append(pinned)
        if archived is not None:
            sql_query += " AND is_archived = %s"
            params.append(archived)
        sql_query += " ORDER BY updated_at DESC"
        results = self.db.execute_query(sql_query, tuple(params))
        threads = []
        for row in results:
            # Map database columns to schema fields
            thread_data = {
                'id': row['thread_id'],
                'sub_room_id': row['sub_room_id'],
                'user_id': 'anonymous',  # Default user_id since it's not in the table
                'title': row['title'],
                'pinned': row['is_pinned'],
                'archived': row['is_archived'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            }
            threads.append(ConversationThread(**thread_data))
        return threads

    def create_message(self, thread_id: str, role: str, content: str, status: str = "draft", model: Optional[str] = None, meta: Optional[Dict[str, Any]] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        message_id = f"msg_{generate_id()}"
        created_at = int(time.time())
        meta_json = json.dumps(meta) if meta else None
        query = """
            INSERT INTO conversation_messages (message_id, thread_id, user_id, role, content, content_searchable, timestamp, meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (message_id, thread_id, user_id, role, content, content, created_at, meta_json)
        self.db.execute_update(query, params)

        thread_update_query = "UPDATE conversation_threads SET updated_at = %s WHERE id = %s"
        self.db.execute_update(thread_update_query, (created_at, thread_id))

        return {"id": message_id, "thread_id": thread_id, "role": role, "content": content, "status": status, "model": model, "meta": meta, "created_at": created_at}

    def update_message(self, message_id: str, content: str, status: str, meta: Dict[str, Any]) -> None:
        meta_json = json.dumps(meta)
        query = "UPDATE conversation_messages SET content = %s, status = %s, meta = %s WHERE id = %s"
        params = (content, status, meta_json, message_id)
        self.db.execute_update(query, params)

    def get_messages_by_thread(self, thread_id: str, cursor: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql_query = "SELECT * FROM conversation_messages WHERE thread_id = %s"
        params: List[Any] = [thread_id]
        if cursor:
            # Assuming cursor is a timestamp value from the 'created_at' field
            sql_query += " AND timestamp < %s"
            params.append(int(cursor))
        sql_query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        results = self.db.execute_query(sql_query, tuple(params))
        for row in results:
            if row and row.get('meta'):
                # meta is already a dict from jsonb, no need to parse unless it's a string
                if isinstance(row['meta'], str):
                    row['meta'] = json.loads(row['meta'])
        return results

    def get_all_messages_by_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        query = "SELECT * FROM conversation_messages WHERE thread_id = %s ORDER BY timestamp ASC"
        params = (thread_id,)
        results = self.db.execute_query(query, params)
        for row in results:
            if row and row.get('meta'):
                if isinstance(row['meta'], str):
                    row['meta'] = json.loads(row['meta'])
        return results

    def get_message_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM conversation_messages WHERE message_id = %s"
        params = (message_id,)
        results = self.db.execute_query(query, params)
        if not results:
            return None
        row = results[0]
        if row and row.get('meta'):
            if isinstance(row['meta'], str):
                row['meta'] = json.loads(row['meta'])
        return row

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
        query = "SELECT * FROM attachments WHERE attachment_id = %s"
        params = (attachment_id,)
        results = self.db.execute_query(query, params)
        return results[0] if results else None

    def create_export_job(self, thread_id: str, user_id: str, format: str) -> Dict[str, Any]:
        job_id = f"exp_{generate_id()}"
        created_at = int(time.time())
        query = """
            INSERT INTO export_jobs (job_id, thread_id, user_id, format, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'queued', %s, %s)
        """
        params = (job_id, thread_id, user_id, format, created_at, created_at)
        self.db.execute_update(query, params)
        return {"id": job_id, "status": "queued"}

    def get_export_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM export_jobs WHERE job_id = %s"
        params = (job_id,)
        results = self.db.execute_query(query, params)
        return results[0] if results else None

    def update_export_job_status(self, job_id: str, status: str, file_url: Optional[str] = None, error_message: Optional[str] = None):
        updated_at = int(time.time())
        query = "UPDATE export_jobs SET status = %s, file_url = %s, error_message = %s, updated_at = %s WHERE job_id = %s"
        params = (status, file_url, error_message, updated_at, job_id)
        self.db.execute_update(query, params)

    def get_room_hierarchy(self, thread_id: str) -> Dict[str, Optional[str]]:
        """
        Given a thread_id, finds the sub_room_id and its parent main_room_id.
        """
        # First, get the room_id from the thread
        thread_query = "SELECT room_id FROM conversation_threads WHERE id = %s"
        thread_result = self.db.execute_query(thread_query, (thread_id,))
        if not thread_result:
            return {"current_room": None, "parent_room": None}

        room_id = thread_result[0].get("room_id")
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
        created_at = int(time.time())
        query = "INSERT INTO attachments (attachment_id, thread_id, filename, content_type, file_size, file_path, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        params = (attachment_id, attachment_data["thread_id"], attachment_data["name"], attachment_data["mime"], attachment_data["size"], attachment_data["url"], created_at)
        self.db.execute_update(query, params)
        return Attachment(id=attachment_id, created_at=created_at, **attachment_data)

# Global service instance
conversation_service: "ConversationService" = None

def get_conversation_service() -> "ConversationService":
    global conversation_service
    if conversation_service is None:
        conversation_service = ConversationService()
    return conversation_service
