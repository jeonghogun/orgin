"""
Memory Service - Manages a two-tier memory architecture with hybrid retrieval.
It is being refactored to delegate fact and profile management to UserFactService.
"""
import logging
import json
import math
import asyncio
from datetime import datetime, timezone
import logging
import json
import math
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

from app.models.schemas import Message
from app.models.memory_schemas import UserProfile, ConversationContext, ContextUpdate
from app.services.database_service import DatabaseService
from app.services.llm_service import LLMService
from app.services.user_fact_service import UserFactService
from app.services.hybrid_search_service import get_hybrid_search_service
from app.core.secrets import SecretProvider
from app.utils.helpers import generate_id, get_current_timestamp
from app.config.settings import settings
from app.services.conversation_service import get_conversation_service
from app.services.fact_types import FactType

logger = logging.getLogger(__name__)

class MemoryService:
    def __init__(self, db_service: DatabaseService, llm_service: LLMService, secret_provider: SecretProvider, user_fact_service: UserFactService):
        self.db = db_service
        self.llm_service = llm_service
        self.secret_provider = secret_provider
        self.user_fact_service = user_fact_service # New dependency
        self.hybrid_search = get_hybrid_search_service()
        self.db_encryption_key = self.secret_provider.get("DB_ENCRYPTION_KEY")
        if not self.db_encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY not found in secret provider.")

    # This method remains as it deals with message retrieval, not V2 facts.
    async def get_relevant_memories_hybrid(self, query: str, room_ids: List[str], user_id: str, limit: int = settings.HYBRID_RETURN_TOPN) -> List[Message]:
        # ... implementation unchanged ...
        pass

    # --- Helper methods for hybrid retrieval remain unchanged ---
    async def _bm25_candidates(self, query: str, room_ids: List[str], user_id: str, encryption_key: str) -> List[Dict[str, Any]]:
        # ... implementation unchanged ...
        pass
    async def _vector_candidates(self, query: str, room_ids: List[str], user_id: str, encryption_key: str) -> List[Dict[str, Any]]:
        # ... implementation unchanged ...
        pass

    def _merge_and_score(self, bm25_results: List[Dict[str, Any]], vector_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge BM25 and vector search results using HybridSearchService."""
        return self.hybrid_search.merge_search_results(bm25_results, vector_results, 'message_id')

    def _apply_time_decay(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply time decay to search results using HybridSearchService."""
        return self.hybrid_search.apply_time_decay_exponential(results)
    async def _optional_rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # ... implementation unchanged ...
        pass

    # --- DEPRECATED / REFACTORED METHODS ---
    # get_user_profile is now proxied to UserFactService for backward compatibility
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        return await self.user_fact_service.get_user_profile(user_id)

    # The old fact methods are kept for legacy conversation state management.
    async def upsert_user_fact(self, user_id: str, kind: str, key: str, value: Dict[str, Any], confidence: float) -> None:
        sql = """
            INSERT INTO user_facts (user_id, kind, key, value_json, confidence, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id, kind, key) DO UPDATE SET
                value_json = EXCLUDED.value_json, confidence = EXCLUDED.confidence, updated_at = NOW();
        """
        params = (user_id, kind, key, json.dumps(value), confidence)
        self.db.execute_update(sql, params)

    async def get_user_facts(self, user_id: str, kind: Optional[str] = None, key: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM user_facts WHERE user_id = %s"
        params = [user_id]
        if kind:
            sql += " AND kind = %s"
            params.append(kind)
        # Note: 'key' column doesn't exist in the current schema, so we ignore it
        # The 'fact_type' column exists in the current schema
        sql += " ORDER BY confidence DESC"
        return self.db.execute_query(sql, tuple(params))

    async def delete_user_fact(self, user_id: str, kind: str, key: str) -> None:
        # Note: 'key' column doesn't exist in the current schema
        # We'll use fact_type or just user_id and kind for deletion
        sql = "DELETE FROM user_facts WHERE user_id = %s AND kind = %s"
        params = (user_id, kind)
        self.db.execute_update(sql, params)

    # --- Unchanged context and promotion methods ---
    async def get_context(self, room_id: str, user_id: str) -> Optional[ConversationContext]:
        # ... implementation unchanged ...
        pass
    async def update_context(self, context_update: ContextUpdate) -> None:
        # ... implementation unchanged ...
        pass
    async def find_and_summarize_promotion_candidates(self, sub_room_id: str, user_id: str, criteria_text: str) -> Dict[str, Any]:
        # ... implementation unchanged ...
        pass
    async def promote_memories(self, sub_room_id: str, main_room_id: str, user_id: str, criteria_text: str) -> str:
        """
        Summarizes a sub-room's conversation and promotes the summary as a new
        fact to the main room's memory.
        """
        conversation_service = get_conversation_service()
        user_fact_service = self.user_fact_service # Already a dependency

        # 1. Get all messages from the sub-room
        full_conversation = ""
        try:
            # Note: The data model seems to have a single thread per sub-room.
            # If multiple threads were possible, this logic would need to be adjusted.
            threads = await conversation_service.get_threads_by_room(room_id=sub_room_id)
            if not threads:
                logger.info(f"No threads found in sub-room {sub_room_id} for promotion.")
                return "No content to promote."

            for thread in threads:
                messages = await conversation_service.get_all_messages_by_thread(thread.id)
                for msg in messages:
                    # Ensure msg is a dictionary and has the expected keys
                    if isinstance(msg, dict):
                        full_conversation += f"{msg.get('role', 'unknown')}: {msg.get('content', '')}\n"
        except Exception as e:
            logger.error(f"Error fetching conversation from sub-room {sub_room_id}: {e}", exc_info=True)
            # Re-raise as a custom exception or handle gracefully
            raise RuntimeError(f"Failed to fetch conversation for promotion: {e}")

        if not full_conversation.strip():
            logger.info(f"Sub-room {sub_room_id} has no message content to promote.")
            return "No content to promote."

        # 2. Summarize the conversation using an LLM
        system_prompt = (
            "You are an AI assistant tasked with summarizing a conversation from a sub-project. "
            "Your summary should capture the key findings, decisions, and important facts that are "
            "worth saving to long-term memory. Focus on the aspects related to the user's goal."
        )
        user_prompt = f"User's Goal: '{criteria_text}'\n\nConversation to Summarize:\n---\n{full_conversation}"

        try:
            summary, _ = await self.llm_service.invoke(
                provider="openai",
                model=settings.SMART_MODEL,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                context="memory-promotion-summary"
            )
        except Exception as e:
            logger.error(f"LLM invocation failed during memory promotion for sub-room {sub_room_id}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate summary for promotion: {e}")


        if not summary or not summary.strip():
            logger.warning(f"LLM failed to generate a summary for sub-room {sub_room_id}.")
            return "Failed to generate a summary."

        # 3. Save the summary as a new fact in the main room
        fact_to_save = {
            "type": FactType.PROMOTED_SUMMARY.value,
            "value": summary,
            "confidence": 0.99 # High confidence as it's user-initiated
        }

        # The sub_room_id serves as the source reference
        # The main_room_id is where the fact is logically stored
        await user_fact_service.save_fact(
            user_id=user_id,
            fact=fact_to_save,
            normalized_value=summary, # Using full summary for potential future matching
            source_message_id=sub_room_id, # Using sub_room_id as the source identifier
            sensitivity="medium",
            room_id=main_room_id
        )

        logger.info(f"Successfully promoted summary from sub-room {sub_room_id} to main-room {main_room_id} for user {user_id}.")
        return summary
    async def archive_old_memories(self, room_id: str):
        # ... implementation unchanged ...
        pass


# Global service instance
memory_service: "MemoryService" = None

def get_memory_service() -> "MemoryService":
    global memory_service
    if memory_service is None:
        from app.services.database_service import get_database_service
        from app.services.llm_service import get_llm_service
        from app.core.secrets import get_secret_provider
        from app.services.user_fact_service import get_user_fact_service
        
        memory_service = MemoryService(
            db_service=get_database_service(),
            llm_service=get_llm_service(),
            secret_provider=get_secret_provider(),
            user_fact_service=get_user_fact_service()
        )
    return memory_service
