"""
Memory Service - Manages a two-tier memory architecture with hybrid retrieval.
It is being refactored to delegate fact and profile management to UserFactService.
"""
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
from app.services.fact_types import FactType
from app.services.storage_service import storage_service

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

    def _build_conversation_snippet(self, messages: List[Message], limit: int = 20) -> str:
        """Create a conversation snippet using the most recent messages."""
        tail = messages[-limit:]
        lines = [f"{msg.role}: {msg.content}" for msg in tail if msg.content]
        return "\n".join(lines)

    def _fallback_summary(self, messages: List[Message]) -> str:
        """Provide a lightweight fallback summary when LLM summarization fails."""
        last_user = next((msg.content for msg in reversed(messages) if msg.role == "user" and msg.content), None)
        if last_user:
            return f"최근 사용자 발화 요약: {last_user[:300]}"
        if messages:
            return f"최근 대화 요약: {messages[-1].content[:300]}"
        return "대화 내용이 충분하지 않습니다."

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
        """Retrieve (or lazily build) the conversation context for a room."""
        query = (
            "SELECT context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at "
            "FROM conversation_contexts WHERE room_id = %s AND user_id = %s"
        )
        try:
            rows = self.db.execute_query(query, (room_id, user_id))
        except Exception as db_error:
            logger.warning(
                "Failed to fetch conversation context (room=%s, user=%s): %s",
                room_id,
                user_id,
                db_error,
                exc_info=True,
            )
            rows = []
        if rows:
            row = rows[0]
            key_topics = row.get("key_topics") or []
            if isinstance(key_topics, str):
                try:
                    key_topics = json.loads(key_topics)
                except json.JSONDecodeError:
                    key_topics = [key_topics]
            return ConversationContext(
                context_id=row["context_id"],
                room_id=row["room_id"],
                user_id=row["user_id"],
                summary=row.get("summary", ""),
                key_topics=key_topics,
                sentiment=row.get("sentiment", "neutral"),
                created_at=row.get("created_at", get_current_timestamp()),
                updated_at=row.get("updated_at", get_current_timestamp()),
            )

        messages = await asyncio.to_thread(storage_service.get_messages, room_id)
        if not messages:
            return None

        conversation_text = self._build_conversation_snippet(messages)

        summary = conversation_text[:500]
        sentiment = "neutral"
        key_topics: List[str] = []

        try:
            llm_payload = (
                "You are an assistant that summarizes conversations. "
                "Return JSON with fields 'summary' (string), 'key_topics' (array of up to 5 short phrases), "
                "and 'sentiment' (one of positive, neutral, negative)."
            )
            user_prompt = (
                "Conversation:\n" + conversation_text + "\n\n"
                "Respond in JSON."
            )
            summary_json, _ = await self.llm_service.invoke(
                provider_name="openai",
                model=settings.LLM_MODEL,
                system_prompt=llm_payload,
                user_prompt=user_prompt,
                request_id="memory-context-summary",
                response_format="json",
            )
            parsed = json.loads(summary_json)
            summary = parsed.get("summary", summary)
            raw_topics = parsed.get("key_topics", [])
            if isinstance(raw_topics, list):
                key_topics = [str(topic) for topic in raw_topics if topic]
            sentiment = parsed.get("sentiment", sentiment)
        except Exception as summarise_error:
            logger.warning(
                "Failed to generate context summary for room %s: %s",
                room_id,
                summarise_error,
            )
            summary = self._fallback_summary(messages)
            key_topics = []
            sentiment = "neutral"

        now_ts = get_current_timestamp()
        context = ConversationContext(
            context_id=generate_id("ctx"),
            room_id=room_id,
            user_id=user_id,
            summary=summary,
            key_topics=key_topics,
            sentiment=sentiment,
            created_at=now_ts,
            updated_at=now_ts,
        )

        insert_query = (
            """
            INSERT INTO conversation_contexts (context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (room_id, user_id) DO UPDATE
            SET summary = EXCLUDED.summary,
                key_topics = EXCLUDED.key_topics,
                sentiment = EXCLUDED.sentiment,
                updated_at = EXCLUDED.updated_at
            """
        )
        params = (
            context.context_id,
            context.room_id,
            context.user_id,
            context.summary,
            context.key_topics,
            context.sentiment,
            context.created_at,
            context.updated_at,
        )
        try:
            self.db.execute_update(insert_query, params)
        except Exception as db_error:
            logger.warning(
                "Failed to upsert conversation context (room=%s, user=%s): %s",
                room_id,
                user_id,
                db_error,
                exc_info=True,
            )
        return context
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
        user_fact_service = self.user_fact_service # Already a dependency

        # 1. Get all messages from the sub-room
        try:
            messages = await asyncio.to_thread(storage_service.get_messages, sub_room_id)
        except Exception as e:
            logger.error(f"Error fetching conversation from sub-room {sub_room_id}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to fetch conversation for promotion: {e}")

        full_conversation = ""
        for msg in messages:
            role = getattr(msg, "role", "unknown")
            content = getattr(msg, "content", "")
            full_conversation += f"{role}: {content}\n"

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
                provider_name="openai",
                model=settings.SMART_MODEL,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                request_id="memory-promotion-summary"
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
