"""
Memory Service - Manages a two-tier memory architecture with hybrid retrieval.
It is being refactored to delegate fact and profile management to UserFactService.
"""
import logging
import json
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any, Set

from rank_bm25 import BM25Okapi

from app.models.schemas import Message
from app.models.memory_schemas import UserProfile, ConversationContext, ContextUpdate, MemoryEntry
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

try:
    _archive_days = int(getattr(settings, "MEMORY_ARCHIVE_AFTER_DAYS", 14))
except (TypeError, ValueError):
    _archive_days = 14
ARCHIVE_WINDOW_DAYS = max(_archive_days, 1)

try:
    _archive_batch = int(getattr(settings, "MEMORY_ARCHIVE_BATCH_SIZE", 200))
except (TypeError, ValueError):
    _archive_batch = 200
ARCHIVE_BATCH_SIZE = max(_archive_batch, 1)

try:
    _archive_min_messages = int(getattr(settings, "MEMORY_ARCHIVE_MIN_MESSAGES", 5))
except (TypeError, ValueError):
    _archive_min_messages = 5
ARCHIVE_MIN_MESSAGES = max(_archive_min_messages, 1)

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
        """Return the most relevant conversation messages using hybrid retrieval."""
        if not query or not room_ids:
            return []

        normalized_room_ids = list(dict.fromkeys(room_ids))
        encryption_key = self.db_encryption_key

        bm25_task = asyncio.create_task(
            self._bm25_candidates(query, normalized_room_ids, user_id, encryption_key)
        )
        vector_task = asyncio.create_task(
            self._vector_candidates(query, normalized_room_ids, user_id, encryption_key)
        )

        bm25_results_raw, vector_results_raw = await asyncio.gather(
            bm25_task, vector_task, return_exceptions=True
        )

        if isinstance(bm25_results_raw, Exception):
            logger.warning("BM25 retrieval failed: %s", bm25_results_raw, exc_info=True)
            bm25_results: List[Dict[str, Any]] = []
        else:
            bm25_results = bm25_results_raw

        if isinstance(vector_results_raw, Exception):
            logger.warning("Vector retrieval failed: %s", vector_results_raw, exc_info=True)
            vector_results: List[Dict[str, Any]] = []
        else:
            vector_results = vector_results_raw

        merged_results = self._merge_and_score(bm25_results, vector_results)
        if not merged_results:
            return []

        decayed_results = self._apply_time_decay(merged_results)
        reranked_results = await self._optional_rerank(query, decayed_results)
        top_results = reranked_results[:limit]

        message_ids = [result["message_id"] for result in top_results if result.get("message_id")]
        if not message_ids:
            return []

        messages = await asyncio.to_thread(self._fetch_messages_by_ids, message_ids)
        message_lookup = {message.message_id: message for message in messages}
        ordered_messages = [message_lookup[msg_id] for msg_id in message_ids if msg_id in message_lookup]
        return ordered_messages

    async def get_relevant_memories(self, room_id: str, user_id: str, query: str, limit: int = 5) -> List[MemoryEntry]:
        """Compatibility layer that projects message-based retrieval into legacy memory entries."""
        messages = await self.get_relevant_memories_hybrid(
            query=query,
            room_ids=[room_id],
            user_id=user_id,
            limit=limit,
        )

        legacy_entries: List[MemoryEntry] = []
        now_ts = get_current_timestamp()
        for index, message in enumerate(messages):
            content = getattr(message, "content", "")
            if not content:
                continue
            message_id = getattr(message, "message_id", None) or generate_id("mem")
            created_at = getattr(message, "timestamp", None) or now_ts
            try:
                timestamp_int = int(created_at)
            except (TypeError, ValueError):
                timestamp_int = now_ts
            legacy_entries.append(
                MemoryEntry(
                    memory_id=str(message_id),
                    room_id=getattr(message, "room_id", room_id),
                    user_id=getattr(message, "user_id", user_id),
                    key=f"message_{index + 1}",
                    value=content,
                    importance=1.0,
                    expires_at=None,
                    created_at=timestamp_int,
                )
            )

        return legacy_entries

    async def build_hierarchical_context_blocks(
        self,
        room_id: str,
        user_id: str,
        query: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Collect conversation summaries and hybrid memories across a room hierarchy."""

        context_blocks: List[Dict[str, Any]] = []
        visited: Set[str] = set()
        room_chain: List[Any] = []

        current_room_id: Optional[str] = room_id
        while current_room_id and current_room_id not in visited:
            visited.add(current_room_id)
            room_obj = await asyncio.to_thread(storage_service.get_room, current_room_id)
            if not room_obj:
                break
            room_chain.append(room_obj)
            current_room_id = getattr(room_obj, "parent_id", None)

        if not room_chain:
            return context_blocks

        seen_contexts: Set[str] = set()
        for room_obj in room_chain:
            try:
                context = await self.get_context(room_obj.room_id, user_id)
            except Exception as context_error:
                logger.warning(
                    "Failed to gather context for room %s hierarchy lookup: %s",
                    room_obj.room_id,
                    context_error,
                    exc_info=True,
                )
                continue

            if not context:
                continue

            summary_parts: List[str] = []
            if getattr(context, "summary", None):
                summary_parts.append(context.summary.strip())
            if getattr(context, "key_topics", None):
                key_topics = [topic for topic in context.key_topics if topic]
                if key_topics:
                    summary_parts.append("키 토픽: " + ", ".join(key_topics))
            sentiment = getattr(context, "sentiment", None)
            if sentiment and sentiment != "neutral":
                summary_parts.append(f"감정: {sentiment}")

            context_text = " ".join(part for part in summary_parts if part).strip()
            if not context_text or context_text in seen_contexts:
                continue

            seen_contexts.add(context_text)
            context_blocks.append(
                {
                    "content": context_text,
                    "room_id": room_obj.room_id,
                    "room_name": getattr(room_obj, "name", room_obj.room_id),
                    "source": "context",
                }
            )

        if query:
            try:
                memories = await self.get_relevant_memories_hybrid(
                    query=query,
                    room_ids=[room.room_id for room in room_chain],
                    user_id=user_id,
                    limit=limit or settings.HYBRID_RETURN_TOPN,
                )
            except Exception as retrieval_error:
                logger.warning(
                    "Failed to gather hybrid memories for hierarchy lookup (room=%s): %s",
                    room_id,
                    retrieval_error,
                    exc_info=True,
                )
                memories = []

            seen_memories: Set[str] = set()
            for memory in memories:
                content = getattr(memory, "content", None) or getattr(memory, "value", None)
                if not content:
                    continue
                normalized = content.strip()
                if not normalized or normalized in seen_memories:
                    continue
                seen_memories.add(normalized)
                room_name = None
                memory_room_id = getattr(memory, "room_id", None)
                for room_obj in room_chain:
                    if room_obj.room_id == memory_room_id:
                        room_name = getattr(room_obj, "name", None)
                        break
                context_blocks.append(
                    {
                        "content": normalized,
                        "room_id": memory_room_id,
                        "room_name": room_name or memory_room_id,
                        "source": "memory",
                    }
                )

        return context_blocks

    async def get_context(self, room_id: str, user_id: str) -> Optional[ConversationContext]:
        """Return the cached conversation context or generate a fresh one from recent messages."""
        try:
            messages = await asyncio.to_thread(storage_service.get_messages, room_id)
        except Exception as fetch_error:
            logger.warning(
                "Failed to load messages for context generation (room=%s, user=%s): %s",
                room_id,
                user_id,
                fetch_error,
                exc_info=True,
            )
            messages = []

        try:
            return await self.get_conversation_context(
                room_id,
                user_id,
                messages,
                force_refresh=False,
            )
        except Exception as context_error:
            logger.warning(
                "Failed to build conversation context (room=%s, user=%s): %s",
                room_id,
                user_id,
                context_error,
                exc_info=True,
            )
            return None

    async def refresh_context(self, room_id: str, user_id: str) -> Optional[ConversationContext]:
        """Force a refresh of the cached conversation context for a room."""
        try:
            messages = await asyncio.to_thread(storage_service.get_messages, room_id)
        except Exception as fetch_error:
            logger.warning(
                "Failed to load messages for context refresh (room=%s, user=%s): %s",
                room_id,
                user_id,
                fetch_error,
                exc_info=True,
            )
            return None

        if not messages:
            return await self.get_conversation_context(
                room_id,
                user_id,
                messages,
                force_refresh=False,
            )

        try:
            return await self.get_conversation_context(
                room_id,
                user_id,
                messages,
                force_refresh=True,
            )
        except Exception as refresh_error:
            logger.warning(
                "Failed to refresh conversation context (room=%s, user=%s): %s",
                room_id,
                user_id,
                refresh_error,
                exc_info=True,
            )
            return None

    # --- Helper methods for hybrid retrieval remain unchanged ---
    async def _bm25_candidates(self, query: str, room_ids: List[str], user_id: str, encryption_key: str) -> List[Dict[str, Any]]:
        if not query or not room_ids:
            return []

        placeholders = ",".join(["%s"] * len(room_ids))
        fetch_limit = max(settings.HYBRID_TOPK_BM25, 1) * 4
        sql = (
            """
            SELECT message_id, room_id, user_id, role,
                   COALESCE(pgp_sym_decrypt(content, %s)::text, content_searchable) AS content,
                   timestamp
            FROM messages
            WHERE room_id IN ({placeholders})
            ORDER BY timestamp DESC
            LIMIT %s
            """.format(placeholders=placeholders)
        )
        params: Tuple[Any, ...] = (encryption_key, *room_ids, fetch_limit)

        try:
            rows = await asyncio.to_thread(self.db.execute_query, sql, params)
        except Exception as db_error:
            logger.warning("BM25 candidate query failed: %s", db_error, exc_info=True)
            return []

        corpus: List[List[str]] = []
        metadata: List[Dict[str, Any]] = []
        for row in rows:
            content = (row.get("content") or "").strip()
            if not content:
                continue
            tokens = content.lower().split()
            if not tokens:
                continue
            corpus.append(tokens)
            metadata.append({
                "message_id": row["message_id"],
                "room_id": row["room_id"],
                "content": content,
                "timestamp": row.get("timestamp"),
            })

        if not corpus:
            return []

        bm25 = BM25Okapi(corpus)
        query_tokens = query.lower().split()
        scores = bm25.get_scores(query_tokens)

        candidates = []
        for meta, score in zip(metadata, scores):
            candidate = meta.copy()
            candidate["score"] = float(score)
            candidates.append(candidate)

        candidates.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return candidates[: settings.HYBRID_TOPK_BM25]

    async def _vector_candidates(self, query: str, room_ids: List[str], user_id: str, encryption_key: str) -> List[Dict[str, Any]]:
        if not query or not room_ids:
            return []

        try:
            embedding, _ = await self.llm_service.generate_embedding(query)
        except Exception as embed_error:
            logger.warning("Vector embedding generation failed: %s", embed_error, exc_info=True)
            return []

        placeholders = ",".join(["%s"] * len(room_ids))
        sql = (
            """
            SELECT message_id, room_id, user_id, role,
                   COALESCE(pgp_sym_decrypt(content, %s)::text, content_searchable) AS content,
                   timestamp,
                   embedding <-> %s AS distance
            FROM messages
            WHERE embedding IS NOT NULL AND room_id IN ({placeholders})
            ORDER BY embedding <-> %s
            LIMIT %s
            """.format(placeholders=placeholders)
        )

        params_list: List[Any] = [encryption_key, embedding]
        params_list.extend(room_ids)
        params_list.append(embedding)
        params_list.append(settings.HYBRID_TOPK_VEC)
        params = tuple(params_list)

        try:
            rows = await asyncio.to_thread(self.db.execute_query, sql, params)
        except Exception as db_error:
            logger.warning("Vector candidate query failed: %s", db_error, exc_info=True)
            return []

        candidates: List[Dict[str, Any]] = []
        for row in rows:
            content = (row.get("content") or "").strip()
            distance = row.get("distance")
            try:
                distance_value = float(distance) if distance is not None else None
            except (TypeError, ValueError):
                distance_value = None
            score = 0.0 if distance_value is None else 1.0 / (1.0 + distance_value)
            candidates.append({
                "message_id": row["message_id"],
                "room_id": row["room_id"],
                "content": content,
                "timestamp": row.get("timestamp"),
                "score": score,
            })

        return candidates

    def _fetch_messages_by_ids(self, message_ids: List[str]) -> List[Message]:
        if not message_ids:
            return []

        placeholders = ",".join(["%s"] * len(message_ids))
        decrypt_query = (
            """
            SELECT message_id, room_id, user_id, role,
                   COALESCE(pgp_sym_decrypt(content, %s)::text, content_searchable) AS content,
                   timestamp
            FROM messages
            WHERE message_id IN ({placeholders})
            """.format(placeholders=placeholders)
        )

        decrypt_params = (self.db_encryption_key, *message_ids)
        try:
            rows = self.db.execute_query(decrypt_query, decrypt_params)
        except Exception as decrypt_error:
            logger.warning("Message decryption failed, falling back to searchable text: %s", decrypt_error)
            fallback_query = (
                """
                SELECT message_id, room_id, user_id, role, content_searchable AS content, timestamp
                FROM messages
                WHERE message_id IN ({placeholders})
                """.format(placeholders=placeholders)
            )
            rows = self.db.execute_query(fallback_query, tuple(message_ids))

        messages: List[Message] = []
        for row in rows:
            raw_timestamp = row.get("timestamp")
            try:
                timestamp = int(raw_timestamp) if raw_timestamp is not None else get_current_timestamp()
            except (TypeError, ValueError):
                timestamp = get_current_timestamp()

            message = Message(
                message_id=row["message_id"],
                room_id=row["room_id"],
                user_id=row["user_id"],
                role=row.get("role", "user"),
                content=(row.get("content") or ""),
                timestamp=timestamp,
            )
            messages.append(message)

        return messages

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
        if not results:
            return []
        if not settings.RERANK_ENABLED:
            return results

        try:
            provider_getter = getattr(self.llm_service, "get_or_create_provider", None)
            if callable(provider_getter):
                provider = provider_getter(settings.RERANK_PROVIDER)
            else:
                provider = self.llm_service.get_provider(settings.RERANK_PROVIDER)
        except Exception as provider_error:
            logger.warning("Rerank provider unavailable: %s", provider_error)
            return results

        if not hasattr(provider, "rerank"):
            logger.info("Provider %s does not support rerank, skipping.", settings.RERANK_PROVIDER)
            return results

        try:
            documents = [
                {"id": item.get("message_id"), "text": item.get("content", ""), "score": item.get("score", 0.0)}
                for item in results
            ]
            top_n = min(settings.RERANK_TOP, len(documents))
            reranked = await provider.rerank(query=query, documents=documents, top_n=top_n)
        except Exception as rerank_error:
            logger.warning("Rerank invocation failed: %s", rerank_error)
            return results

        # Normalize rerank response into an ordered list of IDs
        ranked_ids: List[str] = []
        if isinstance(reranked, dict):
            candidates = reranked.get("results") or reranked.get("data") or []
        else:
            candidates = reranked

        for item in candidates or []:
            item_id = None
            if isinstance(item, dict):
                item_id = item.get("id") or item.get("document_id") or item.get("index")
            if item_id:
                ranked_ids.append(str(item_id))

        if not ranked_ids:
            return results

        result_lookup = {item.get("message_id"): item for item in results}
        reranked_results = [result_lookup[item_id] for item_id in ranked_ids if item_id in result_lookup]
        remaining = [item for item in results if item.get("message_id") not in ranked_ids]
        return reranked_results + remaining

    # --- DEPRECATED / REFACTORED METHODS ---
    # get_user_profile is now proxied to UserFactService for backward compatibility
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        return await self.user_fact_service.get_user_profile(user_id)

    # The old fact methods are kept for legacy conversation state management.
    async def upsert_user_fact(self, user_id: str, kind: str, key: str, value: Dict[str, Any], confidence: float) -> None:
        """Persist lightweight conversation facts using the v2 schema."""

        normalized_value = value.get("normalized") or value.get("normalized_value") or key
        sensitivity = value.get("sensitivity", "low")
        sql = """
            INSERT INTO user_facts (user_id, kind, fact_type, value_json, confidence, normalized_value, latest, pending_review, sensitivity, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, FALSE, %s, NOW())
            ON CONFLICT (user_id, kind, fact_type) DO UPDATE SET
                value_json = EXCLUDED.value_json,
                confidence = EXCLUDED.confidence,
                normalized_value = EXCLUDED.normalized_value,
                latest = TRUE,
                pending_review = FALSE,
                sensitivity = EXCLUDED.sensitivity,
                updated_at = NOW();
        """
        params = (
            user_id,
            kind,
            key,
            json.dumps(value),
            confidence,
            normalized_value,
            sensitivity,
        )
        try:
            await asyncio.to_thread(self.db.execute_update, sql, params)
        except Exception as db_error:
            logger.warning(
                "Failed to upsert user fact v2 (user=%s, key=%s): %s",
                user_id,
                key,
                db_error,
                exc_info=True,
            )


    async def get_conversation_context(
        self,
        room_id: str,
        user_id: str,
        messages: List[Message],
        force_refresh: bool = False,
    ) -> Optional[ConversationContext]:
        """Fetch, or create and summarize, a conversation context."""
        query = "SELECT * FROM conversation_contexts WHERE room_id = %s AND user_id = %s"
        params = (room_id, user_id)
        rows = self.db.execute_query(query, params)

        existing_row = rows[0] if rows else None

        if existing_row and not force_refresh:
            return ConversationContext(
                context_id=existing_row["context_id"],
                room_id=existing_row["room_id"],
                user_id=existing_row["user_id"],
                summary=existing_row.get("summary", ""),
                key_topics=existing_row.get("key_topics", []),
                sentiment=existing_row.get("sentiment", "neutral"),
                created_at=existing_row.get("created_at"),
                updated_at=existing_row.get("updated_at"),
            )

        if not messages:
            if existing_row:
                return ConversationContext(
                    context_id=existing_row["context_id"],
                    room_id=existing_row["room_id"],
                    user_id=existing_row["user_id"],
                    summary=existing_row.get("summary", ""),
                    key_topics=existing_row.get("key_topics", []),
                    sentiment=existing_row.get("sentiment", "neutral"),
                    created_at=existing_row.get("created_at"),
                    updated_at=get_current_timestamp(),
                )
            return None

        conversation_snippet = self._build_conversation_snippet(messages)
        system_prompt = (
            "You are an AI assistant that summarizes conversations. "
            "Identify the main topics, user sentiment, and provide a concise summary."
        )
        user_prompt = f"Conversation snippet:\n{conversation_snippet}"
        try:
            llm_response, _ = await self.llm_service.invoke(
                provider_name="openai",
                model=settings.LLM_MODEL,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                request_id=f"get-context-{room_id}",
            )
            # Assuming LLM returns a JSON-like string
            response_data = json.loads(llm_response)
        except Exception as e:
            logger.warning(
                "LLM context summarization failed for room %s, user %s: %s",
                room_id,
                user_id,
                e,
                exc_info=True,
            )
            response_data = {}

        now = get_current_timestamp()
        context_id = existing_row["context_id"] if existing_row else generate_id("ctx")
        created_at = existing_row.get("created_at") if existing_row else now
        if not created_at:
            created_at = now
        context = ConversationContext(
            context_id=context_id,
            room_id=room_id,
            user_id=user_id,
            summary=response_data.get("summary", self._fallback_summary(messages)),
            key_topics=response_data.get("key_topics", []),
            sentiment=response_data.get("sentiment", "neutral"),
            created_at=created_at,
            updated_at=now,
        )

        insert_query = (
            """
            INSERT INTO conversation_contexts (context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (room_id, user_id) DO UPDATE SET
                summary = EXCLUDED.summary,
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
        """Update or create a conversation context row and optionally persist extracted memories."""
        room_id = context_update.room_id
        user_id = context_update.user_id

        summary = context_update.summary if context_update.summary is not None else None
        if summary is not None:
            summary = summary.strip()

        key_topics = None
        if context_update.key_topics is not None:
            key_topics = [topic.strip() for topic in context_update.key_topics if topic and topic.strip()]

        sentiment = context_update.sentiment if context_update.sentiment is not None else None
        if sentiment is not None:
            sentiment = sentiment.strip() or "neutral"

        has_context_update = any(
            value is not None for value in (summary, key_topics, sentiment)
        )

        now_ts = get_current_timestamp()

        if has_context_update:
            existing_rows = self.db.execute_query(
                "SELECT context_id FROM conversation_contexts WHERE room_id = %s AND user_id = %s",
                (room_id, user_id),
            )

            if existing_rows:
                set_clauses: List[str] = []
                params: List[Any] = []
                if summary is not None:
                    set_clauses.append("summary = %s")
                    params.append(summary)
                if key_topics is not None:
                    set_clauses.append("key_topics = %s")
                    params.append(key_topics)
                if sentiment is not None:
                    set_clauses.append("sentiment = %s")
                    params.append(sentiment)
                set_clauses.append("updated_at = %s")
                params.append(now_ts)
                params.extend([room_id, user_id])

                update_query = f"UPDATE conversation_contexts SET {', '.join(set_clauses)} WHERE room_id = %s AND user_id = %s"
                try:
                    self.db.execute_update(update_query, tuple(params))
                except Exception as db_error:
                    logger.warning(
                        "Failed to update conversation context (room=%s, user=%s): %s",
                        room_id,
                        user_id,
                        db_error,
                        exc_info=True,
                    )
            else:
                insert_query = (
                    """
                    INSERT INTO conversation_contexts (context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                )
                params = (
                    generate_id("ctx"),
                    room_id,
                    user_id,
                    summary or "",
                    key_topics or [],
                    sentiment or "neutral",
                    now_ts,
                    now_ts,
                )
                try:
                    self.db.execute_update(insert_query, params)
                except Exception as db_error:
                    logger.warning(
                        "Failed to insert conversation context (room=%s, user=%s): %s",
                        room_id,
                        user_id,
                        db_error,
                        exc_info=True,
                    )

        new_memory = context_update.new_memory or {}
        memory_value = new_memory.get("value") or new_memory.get("content")
        if memory_value:
            fact_key = new_memory.get("key") or new_memory.get("type") or "context_note"
            fact_kind = new_memory.get("kind") or "context"
            try:
                confidence = float(new_memory.get("confidence", 0.6))
            except (TypeError, ValueError):
                confidence = 0.6
            fact_payload = {
                "value": memory_value,
                "source": new_memory.get("source", "context_update"),
            }
            if summary:
                fact_payload["summary"] = summary
            try:
                await self.upsert_user_fact(
                    user_id=user_id,
                    kind=fact_kind,
                    key=fact_key,
                    value=fact_payload,
                    confidence=confidence,
                )
            except Exception as fact_error:
                logger.warning(
                    "Failed to persist contextual memory for user %s in room %s: %s",
                    user_id,
                    room_id,
                    fact_error,
                    exc_info=True,
                )

    async def find_and_summarize_promotion_candidates(self, sub_room_id: str, user_id: str, criteria_text: str) -> Dict[str, Any]:
        """Return a lightweight summary and candidate messages for manual promotion flows."""
        try:
            messages = await asyncio.to_thread(storage_service.get_messages, sub_room_id)
        except Exception as fetch_error:
            logger.error(
                "Failed to fetch messages for promotion candidates (room=%s, user=%s): %s",
                sub_room_id,
                user_id,
                fetch_error,
                exc_info=True,
            )
            return {
                "status": "error",
                "summary": "",
                "candidates": [],
                "error": str(fetch_error),
            }

        if not messages:
            return {
                "status": "empty",
                "summary": "",
                "candidates": [],
                "total_messages": 0,
                "keywords": [],
            }

        transcript_lines = [f"{msg.role}: {msg.content}" for msg in messages if getattr(msg, "content", "").strip()]
        transcript = "\n".join(transcript_lines)

        keyword_candidates = [token.lower() for token in re.findall(r"\w+", criteria_text) if len(token) > 2]
        filtered_messages: List[Dict[str, Any]] = []
        for message in messages:
            content = getattr(message, "content", "")
            if not content:
                continue
            lower_content = content.lower()
            if not keyword_candidates or any(keyword in lower_content for keyword in keyword_candidates):
                filtered_messages.append(
                    {
                        "message_id": message.message_id,
                        "role": message.role,
                        "content": content,
                        "timestamp": message.timestamp,
                    }
                )

        summary = ""
        system_prompt = (
            "You are an AI assistant that prepares candidate summaries for promoting sub-room discussions into long-term memory. "
            "Produce a concise paragraph that captures the most important facts, decisions, and follow-up items that align with the user's goal."
        )
        user_prompt = (
            f"User goal or criteria: {criteria_text}\n\n" \
            "Conversation transcript:\n" + transcript
        )
        try:
            summary, _ = await self.llm_service.invoke(
                provider_name="openai",
                model=settings.LLM_MODEL,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                request_id="memory-promotion-candidates",
            )
        except Exception as llm_error:
            logger.warning(
                "Failed to summarize promotion candidates for room %s: %s",
                sub_room_id,
                llm_error,
            )
            summary = self._fallback_summary(messages)

        return {
            "status": "ok" if filtered_messages else "no_candidates",
            "summary": summary.strip(),
            "candidates": filtered_messages[:20],
            "total_messages": len(messages),
            "total_candidates": len(filtered_messages),
            "keywords": keyword_candidates,
        }
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
            "You are an AI assistant that summarizes a detailed conversation from a sub-room "
            "to be promoted into the main conversation's long-term memory. "
            "Your summary should be concise, factual, and capture the key outcomes, decisions, or important information "
            f"that aligns with the user's stated goal for this sub-room: '{criteria_text}'"
        )
        user_prompt = f"Conversation to summarize:\n\n{full_conversation}"
        try:
            summary, _ = await self.llm_service.invoke(
                provider_name="openai",
                model=settings.LLM_MODEL,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                request_id=f"promote-memories-{sub_room_id}",
            )
        except Exception as e:
            logger.error(f"Error summarizing conversation from sub-room {sub_room_id}: {e}", exc_info=True)
            summary = self._fallback_summary(messages) # Fallback

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
        """Summarize and archive messages that fall outside the active memory window."""
        cutoff_seconds = ARCHIVE_WINDOW_DAYS * 24 * 60 * 60
        cutoff_timestamp = get_current_timestamp() - cutoff_seconds

        fetch_query = (
            """
            SELECT message_id, room_id, user_id, role,
                   COALESCE(pgp_sym_decrypt(content, %s)::text, content_searchable) AS content,
                   timestamp
            FROM messages
            WHERE room_id = %s AND timestamp < %s
            ORDER BY timestamp ASC
            LIMIT %s
            """
        )
        params = (self.db_encryption_key, room_id, cutoff_timestamp, ARCHIVE_BATCH_SIZE)
        try:
            rows = self.db.execute_query(fetch_query, params)
        except Exception as db_error:
            logger.warning("Failed to load messages for archival (room=%s): %s", room_id, db_error, exc_info=True)
            return

        messages: List[Message] = []
        for row in rows:
            content = (row.get("content") or "").strip()
            if not content:
                continue
            try:
                timestamp = int(row.get("timestamp", 0))
            except (TypeError, ValueError):
                timestamp = get_current_timestamp()
            messages.append(
                Message(
                    message_id=row["message_id"],
                    room_id=row["room_id"],
                    user_id=row["user_id"],
                    role=row.get("role", "user"),
                    content=content,
                    timestamp=timestamp,
                )
            )

        if len(messages) < ARCHIVE_MIN_MESSAGES:
            logger.debug(
                "Skipping archival for room %s (messages available: %s, minimum required: %s)",
                room_id,
                len(messages),
                ARCHIVE_MIN_MESSAGES,
            )
            return

        transcript = "\n".join(f"{msg.role}: {msg.content}" for msg in messages)
        system_prompt = (
            "You compress historical chat logs into long-term memory. "
            "Write a concise summary (3-5 sentences) emphasising facts, decisions, and follow-ups that should be remembered."
        )
        user_prompt = "Conversation transcript:\n" + transcript
        try:
            summary, _ = await self.llm_service.invoke(
                provider_name="openai",
                model=settings.LLM_MODEL,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                request_id=f"memory-archive-{room_id}",
            )
        except Exception as llm_error:
            logger.warning("Failed to generate archive summary for room %s: %s", room_id, llm_error)
            summary = self._fallback_summary(messages)

        summary = (summary or "").strip()
        if not summary:
            logger.debug("Generated archive summary was empty for room %s; skipping archival.", room_id)
            return

        try:
            embedding, _ = await self.llm_service.generate_embedding(summary)
        except Exception as embed_error:
            logger.warning("Failed to generate embedding for archive summary (room=%s): %s", room_id, embed_error)
            return

        try:
            room = await asyncio.to_thread(storage_service.get_room, room_id)
        except Exception:
            room = None

        archive_user_id = getattr(room, "owner_id", None) or messages[0].user_id
        created_at = get_current_timestamp()
        memory_id = generate_id("mem")
        memory_key = f"archive_before_{cutoff_timestamp}"

        insert_query = (
            """
            INSERT INTO memories (memory_id, user_id, room_id, key, value, embedding, importance, expires_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        )
        insert_params = (
            memory_id,
            archive_user_id,
            room_id,
            memory_key,
            summary,
            embedding,
            0.6,
            None,
            created_at,
        )
        try:
            self.db.execute_update(insert_query, insert_params)
        except Exception as db_error:
            logger.warning("Failed to persist archive summary for room %s: %s", room_id, db_error, exc_info=True)
            return

        message_ids = [msg.message_id for msg in messages]
        placeholders = ",".join(["%s"] * len(message_ids))
        delete_query = f"DELETE FROM messages WHERE message_id IN ({placeholders})"
        try:
            deleted_count = self.db.execute_update(delete_query, tuple(message_ids))
        except Exception as db_error:
            logger.warning("Failed to delete archived messages for room %s: %s", room_id, db_error, exc_info=True)
            return

        if deleted_count:
            update_room_query = "UPDATE rooms SET message_count = GREATEST(message_count - %s, 0), updated_at = %s WHERE room_id = %s"
            try:
                self.db.execute_update(update_room_query, (deleted_count, created_at, room_id))
            except Exception as db_error:
                logger.warning("Failed to update room statistics after archival (room=%s): %s", room_id, db_error, exc_info=True)


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