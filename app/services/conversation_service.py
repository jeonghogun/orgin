"""Service layer for handling conversation logic backed by raw SQL."""
import logging
from typing import List, Optional, Dict, Any

from app.models.conversation_schemas import Attachment, ConversationThread, ConversationThreadCreate
from app.services.conversation_repository import ConversationRepository, get_conversation_repository
from app.services.token_usage_tracker import TokenUsageTracker

logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(
        self,
        repository: Optional[ConversationRepository] = None,
        token_tracker: Optional[TokenUsageTracker] = None,
    ):
        self.repository = repository or get_conversation_repository()
        self.token_tracker = token_tracker or TokenUsageTracker()

    @property
    def redis_client(self):
        """Expose the underlying Redis client for compatibility with existing tests."""
        return self.token_tracker.redis_client if self.token_tracker else None

    @redis_client.setter
    def redis_client(self, value) -> None:
        if not self.token_tracker:
            self.token_tracker = TokenUsageTracker()
        self.token_tracker.redis_client = value

    def increment_token_usage(self, user_id: str, token_count: int) -> int:
        """Increments a user's token usage for the day in Redis."""
        if not self.token_tracker:
            return 0
        return self.token_tracker.increment_usage(user_id, token_count)

    def get_today_usage(self, user_id: str) -> int:
        """Gets a user's token usage for the day from Redis."""
        if not self.token_tracker:
            return 0
        return self.token_tracker.get_usage(user_id)

    def create_thread(self, room_id: str, user_id: str, thread_data: ConversationThreadCreate) -> ConversationThread:
        thread = self.repository.create_thread(room_id, user_id, thread_data.title)
        try:
            self.repository.touch_room(room_id)
        except Exception as exc:
            logger.warning("Failed to bump parent room timestamp for %s: %s", room_id, exc)
        return thread

    async def get_threads_by_room(self, room_id: str, query: Optional[str] = None, pinned: Optional[bool] = None, archived: Optional[bool] = None) -> List[ConversationThread]:
        return await self.repository.list_threads(room_id, query_text=query, pinned=pinned, archived=archived)

    def create_message(self, thread_id: str, role: str, content: str, status: str = "draft", model: Optional[str] = None, meta: Optional[Dict[str, Any]] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        return self.repository.create_message(
            thread_id,
            role,
            content,
            status=status,
            model=model,
            meta=meta,
            user_id=user_id,
        )

    def update_thread(
        self,
        thread_id: str,
        updates: Optional[Dict[str, Any]] = None,
        *,
        title: Optional[str] = None,
        pinned: Optional[bool] = None,
        archived: Optional[bool] = None,
    ) -> Optional[ConversationThread]:
        """Update thread metadata supporting both legacy dict payloads and keyword args."""

        # Allow callers to pass the legacy dict payload while still supporting keyword usage
        merged_updates: Dict[str, Any] = {}
        if isinstance(updates, dict):
            merged_updates.update(updates)

        if title is not None:
            merged_updates["title"] = title
        if pinned is not None:
            merged_updates["pinned"] = pinned
        if archived is not None:
            merged_updates["archived"] = archived

        # Accept historical field names from earlier API versions
        if "is_pinned" in merged_updates and "pinned" not in merged_updates:
            merged_updates["pinned"] = merged_updates["is_pinned"]
        if "is_archived" in merged_updates and "archived" not in merged_updates:
            merged_updates["archived"] = merged_updates["is_archived"]

        return self.repository.update_thread(thread_id, merged_updates)

    def delete_thread(self, thread_id: str) -> bool:
        return self.repository.delete_thread(thread_id)

    def get_thread_by_id(self, thread_id: str) -> Optional[ConversationThread]:
        return self.repository.get_thread(thread_id)

    def update_message(self, message_id: str, content: str, status: str, meta: Dict[str, Any]) -> None:
        self.repository.update_message_content(message_id, content, status, meta)

    def search_messages(
        self,
        query: str,
        *,
        thread_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        return self.repository.search_messages(query, thread_id=thread_id, limit=limit)

    def get_messages_by_thread(self, thread_id: str, cursor: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return self.repository.list_messages(thread_id, cursor=cursor, limit=limit)

    async def get_all_messages_by_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        return await self.repository.list_all_messages(thread_id)

    def get_message_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        return self.repository.get_message(message_id)

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
        return self.repository.get_attachment(attachment_id)

    def create_export_job(self, thread_id: str, user_id: str, format: str) -> Dict[str, Any]:
        return self.repository.create_export_job(thread_id, user_id, format)

    def get_export_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.repository.get_export_job(job_id)

    def update_export_job_status(self, job_id: str, status: str, file_url: Optional[str] = None, error_message: Optional[str] = None):
        self.repository.update_export_job(job_id, status, file_url=file_url, error_message=error_message)

    def get_room_hierarchy(self, thread_id: str) -> Dict[str, Optional[str]]:
        return self.repository.get_room_hierarchy(thread_id)

    def get_message_versions(self, message_id: str) -> List[Dict[str, Any]]:
        return self.repository.list_message_versions(message_id)

    def create_attachment(self, attachment_data: Dict[str, Any], thread_id: Optional[str] = None) -> Attachment:
        return self.repository.create_attachment(attachment_data, thread_id=thread_id)

# Global service instance
conversation_service: "ConversationService" = None

def get_conversation_service() -> "ConversationService":
    global conversation_service
    if conversation_service is None:
        conversation_service = ConversationService()
    return conversation_service
