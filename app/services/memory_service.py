"""
Memory Service - Manages a two-tier memory architecture with hybrid retrieval.
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
from app.core.secrets import SecretProvider
from app.utils.helpers import generate_id, get_current_timestamp
from app.config.settings import settings

logger = logging.getLogger(__name__)

class MemoryService:
    def __init__(self, db_service: DatabaseService, llm_service: LLMService, secret_provider: SecretProvider):
        self.db = db_service
        self.llm_service = llm_service
        self.secret_provider = secret_provider
        self.db_encryption_key = self.secret_provider.get("DB_ENCRYPTION_KEY")
        if not self.db_encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY not found in secret provider.")

    async def get_relevant_memories_hybrid(self, query: str, room_ids: List[str], user_id: str, limit: int = settings.HYBRID_RETURN_TOPN) -> List[Message]:
        bm25_candidates_task = self._bm25_candidates(query, room_ids, user_id)
        vector_candidates_task = self._vector_candidates(query, room_ids, user_id)
        bm25_results, vector_results = await asyncio.gather(bm25_candidates_task, vector_candidates_task)
        merged_results = self._merge_and_score(bm25_results, vector_results)
        if settings.TIME_DECAY_ENABLED:
            merged_results = self._apply_time_decay(merged_results)
        merged_results.sort(key=lambda x: x['score'], reverse=True)
        if settings.RERANK_ENABLED:
            merged_results = await self._optional_rerank(query, merged_results)
        final_results_data = merged_results[:limit]
        for result in final_results_data:
            result['content'] = self._decrypt_content(result['content'])
        return [Message(**msg) for msg in final_results_data]

    def _decrypt_content(self, encrypted_content: bytes) -> str:
        if not encrypted_content: return ""
        query = "SELECT pgp_sym_decrypt(%s, %s) as decrypted"
        params = (encrypted_content, self.db_encryption_key)
        result = self.db.execute_query(query, params)
        return result[0]['decrypted'] if result else ""

    async def _bm25_candidates(self, query: str, room_ids: List[str], user_id: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT message_id, room_id, user_id, role, content, timestamp, ts_rank_cd(ts, plainto_tsquery('simple', %s)) as score
            FROM messages WHERE room_id = ANY(%s) AND user_id = %s AND ts @@ plainto_tsquery('simple', %s)
            ORDER BY score DESC LIMIT %s;
        """
        params = (query, room_ids, user_id, query, settings.HYBRID_TOPK_BM25)
        return self.db.execute_query(sql, params)

    async def _vector_candidates(self, query: str, room_ids: List[str], user_id: str) -> List[Dict[str, Any]]:
        query_embedding, _ = await self.llm_service.generate_embedding(query)
        sql = """
            SELECT message_id, room_id, user_id, role, content, timestamp, 1 - (embedding <=> %s::vector) as score
            FROM messages WHERE room_id = ANY(%s) AND user_id = %s AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector LIMIT %s;
        """
        params = (query_embedding, room_ids, user_id, query_embedding, settings.HYBRID_TOPK_VEC)
        return self.db.execute_query(sql, params)

    def _normalize_scores(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scores = [r['score'] for r in results if r.get('score') is not None]
        if not scores: return results
        min_score, max_score = min(scores), max(scores)
        if max_score == min_score:
            for r in results: r['score'] = 0.5
            return results
        for r in results:
            r['score'] = (r.get('score', 0) - min_score) / (max_score - min_score)
        return results

    def _merge_and_score(self, bm25_results: List[Dict[str, Any]], vector_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bm25_results = self._normalize_scores(bm25_results)
        vector_results = self._normalize_scores(vector_results)
        all_results: Dict[str, Dict[str, Any]] = {}
        for r in bm25_results:
            all_results[r['message_id']] = {**r, 'score': r.get('score', 0) * settings.HYBRID_BM25_WEIGHT}
        for r in vector_results:
            if r['message_id'] in all_results:
                all_results[r['message_id']]['score'] += r.get('score', 0) * settings.HYBRID_VEC_WEIGHT
            else:
                all_results[r['message_id']] = {**r, 'score': r.get('score', 0) * settings.HYBRID_VEC_WEIGHT}
        return list(all_results.values())

    def _apply_time_decay(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now_ts = datetime.now(timezone.utc).timestamp()
        for r in results:
            age_days = (now_ts - r['timestamp']) / (60 * 60 * 24)
            decay_factor = math.exp(-settings.TIME_DECAY_LAMBDA * age_days)
            r['score'] *= decay_factor
        return results

    async def _optional_rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        logger.info("Reranking step is enabled (logic not yet implemented).")
        return results

    async def upsert_user_fact(self, user_id: str, kind: str, key: str, value: Dict[str, Any], confidence: float) -> None:
        sql = """
            INSERT INTO user_facts (user_id, kind, key, value_json, confidence, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id, kind, key) DO UPDATE SET
                value_json = EXCLUDED.value_json, confidence = EXCLUDED.confidence, updated_at = NOW();
        """
        params = (user_id, kind, key, json.dumps(value), confidence)
        self.db.execute_update(sql, params)

    async def get_user_facts(self, user_id: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        if kind:
            sql = "SELECT * FROM user_facts WHERE user_id = %s AND kind = %s ORDER BY confidence DESC"
            params = (user_id, kind)
        else:
            sql = "SELECT * FROM user_facts WHERE user_id = %s ORDER BY confidence DESC"
            params = (user_id,)
        return self.db.execute_query(sql, params)

    async def get_context(self, room_id: str, user_id: str) -> Optional[ConversationContext]:
        """Get conversation context for a room and user"""
        try:
            query = """
                SELECT context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at
                FROM conversation_contexts 
                WHERE room_id = %s AND user_id = %s
                ORDER BY updated_at DESC 
                LIMIT 1
            """
            results = self.db.execute_query(query, (room_id, user_id))
            
            if not results:
                return None
                
            row = results[0]
            return ConversationContext(
                context_id=row["context_id"],
                room_id=row["room_id"],
                user_id=row["user_id"],
                summary=row["summary"] or "",
                key_topics=row["key_topics"] if row["key_topics"] else [],  # PostgreSQL 배열을 직접 사용
                sentiment=row["sentiment"] or "neutral",
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
        except Exception as e:
            logger.error(f"Failed to get conversation context for room {room_id}, user {user_id}: {e}")
            return None

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        key = self.db_encryption_key
        try:
            query = """
                SELECT user_id, role, pgp_sym_decrypt(name, %s::text) as name,
                       pgp_sym_decrypt(preferences, %s::text) as preferences,
                       conversation_style, interests, created_at, updated_at
                FROM user_profiles WHERE user_id = %s
            """
            params = (key, key, user_id)
            results = self.db.execute_query(query, params)
            if results:
                profile_data = results[0]
                profile_data['preferences'] = json.loads(profile_data['preferences']) if profile_data.get('preferences') else {}
                profile_data['interests'] = profile_data.get('interests') or []
                return UserProfile(**profile_data)

            logger.info(f"No profile found for user '{user_id}'. Creating a default one.")
            new_profile = UserProfile(user_id=user_id, created_at=get_current_timestamp(), updated_at=get_current_timestamp())
            insert_query = """
                INSERT INTO user_profiles (user_id, role, name, preferences, conversation_style, interests, created_at, updated_at)
                VALUES (%s, %s, pgp_sym_encrypt(%s, %s::text), pgp_sym_encrypt(%s, %s::text), %s, %s, %s, %s)
            """
            insert_params = (
                new_profile.user_id, new_profile.role, new_profile.name, key,
                json.dumps(new_profile.preferences), key, new_profile.conversation_style,
                new_profile.interests, new_profile.created_at, new_profile.updated_at
            )
            self.db.execute_update(insert_query, insert_params)
            return new_profile
        except Exception as e:
            logger.error(f"Failed to get or create user profile for '{user_id}': {e}", exc_info=True)
            return None

    async def update_context(self, context_update: ContextUpdate) -> None:
        """Update conversation context"""
        try:
            # Check if context exists
            existing_context = await self.get_context(context_update.room_id, context_update.user_id)
            
            if existing_context:
                # Update existing context
                update_fields = []
                params = []
                
                if context_update.summary is not None:
                    update_fields.append("summary = %s")
                    params.append(context_update.summary)
                
                if context_update.key_topics is not None:
                    update_fields.append("key_topics = %s")
                    params.append(context_update.key_topics)  # PostgreSQL 배열로 직접 전달
                
                if context_update.sentiment is not None:
                    update_fields.append("sentiment = %s")
                    params.append(context_update.sentiment)
                
                if update_fields:
                    update_fields.append("updated_at = %s")
                    params.extend([get_current_timestamp(), context_update.room_id, context_update.user_id])
                    
                    query = f"""
                        UPDATE conversation_contexts 
                        SET {', '.join(update_fields)}
                        WHERE room_id = %s AND user_id = %s
                    """
                    self.db.execute_update(query, tuple(params))
            else:
                # Create new context
                context_id = generate_id()
                current_time = get_current_timestamp()
                
                query = """
                    INSERT INTO conversation_contexts 
                    (context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    context_id,
                    context_update.room_id,
                    context_update.user_id,
                    context_update.summary or "",
                    context_update.key_topics or [],  # PostgreSQL 배열로 직접 전달
                    context_update.sentiment or "neutral",
                    current_time,
                    current_time
                )
                self.db.execute_update(query, params)
                
        except Exception as e:
            logger.error(f"Failed to update context: {e}")
            raise

    async def update_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> Optional[UserProfile]:
        key = self.db_encryption_key
        if not profile_data: return await self.get_user_profile(user_id)
        profile_data["updated_at"] = get_current_timestamp()
        set_clauses, params, encrypted_fields = [], [], {"name", "preferences"}

        for field, value in profile_data.items():
            if field in encrypted_fields:
                value_to_encrypt = json.dumps(value) if field == "preferences" else value
                if value_to_encrypt is not None:
                    set_clauses.append(f"{field} = pgp_sym_encrypt(%s, %s)")
                    params.extend([value_to_encrypt, key])
                else: set_clauses.append(f"{field} = NULL")
            else:
                set_clauses.append(f"{field} = %s")
                params.append(value)

        if not set_clauses: return await self.get_user_profile(user_id)
        query = f"UPDATE user_profiles SET {', '.join(set_clauses)} WHERE user_id = %s"
        params.append(user_id)
        try:
            self.db.execute_update(query, tuple(params))
            logger.info(f"Successfully updated profile for user '{user_id}'.")
            return await self.get_user_profile(user_id)
        except Exception as e:
            logger.error(f"Failed to update profile for user '{user_id}': {e}", exc_info=True)
            return None

    # The archival methods are placeholders for now and will be implemented next.
    async def archive_old_memories(self, room_id: str):
        logger.info(f"Archival process placeholder for room {room_id}")
        pass
