"""
Memory and Context Management Service
"""

import sqlite3
import json
import logging
from typing import List, Optional
import redis.asyncio as redis  # type: ignore
from contextlib import asynccontextmanager

from app.models.memory_schemas import (
    ConversationContext,
    UserProfile,
    MemoryEntry,
    ContextUpdate,
)
from app.utils.helpers import generate_id, get_current_timestamp

logger = logging.getLogger(__name__)


class MemoryService:
    """메모리 및 맥락 관리 서비스"""

    def __init__(
        self, db_path: str = "data/memory.db", redis_url: str = "redis://localhost:6379"
    ):
        super().__init__()
        self.db_path = db_path
        self.redis_url = redis_url
        self._redis_client: Optional[redis.Redis] = None
        self._init_database()

    def _init_database(self):
        """SQLite 데이터베이스 초기화"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversation_contexts (
                        context_id TEXT PRIMARY KEY,
                        room_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        summary TEXT,
                        key_topics TEXT,
                        sentiment TEXT DEFAULT 'neutral',
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                """
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id TEXT PRIMARY KEY,
                        name TEXT,
                        preferences TEXT,
                        conversation_style TEXT DEFAULT 'casual',
                        interests TEXT,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                """
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_entries (
                        memory_id TEXT PRIMARY KEY,
                        room_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        memory_key TEXT NOT NULL,
                        memory_value TEXT NOT NULL,
                        importance REAL DEFAULT 1.0,
                        expires_at INTEGER,
                        created_at INTEGER NOT NULL
                    )
                """
                )

                # 인덱스 생성
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_context_room_user ON conversation_contexts(room_id, user_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memory_room_user ON memory_entries(room_id, user_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memory_expires ON memory_entries(expires_at)"
                )

                conn.commit()
                logger.info("Memory database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize memory database: {e}")

    @asynccontextmanager
    async def get_redis_client(self):
        """Redis 클라이언트 컨텍스트 매니저"""
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(self.redis_url)  # type: ignore
                await self._redis_client.ping()  # type: ignore
                logger.info("Redis connection established")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._redis_client = None

        try:
            yield self._redis_client
        except Exception as e:
            logger.error(f"Redis operation failed: {e}")
            raise

    async def get_context(
        self, room_id: str, user_id: str
    ) -> Optional[ConversationContext]:
        """대화 맥락 조회"""
        try:
            # 먼저 Redis에서 조회
            async with self.get_redis_client() as redis_client:
                if redis_client:
                    cache_key = f"context:{room_id}:{user_id}"
                    cached = await redis_client.get(cache_key)
                    if cached:
                        data = json.loads(cached)
                        return ConversationContext(**data)

            # SQLite에서 조회
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM conversation_contexts
                    WHERE room_id = ? AND user_id = ?
                    ORDER BY updated_at DESC LIMIT 1
                """,
                    (room_id, user_id),
                )

                row = cursor.fetchone()
                if row:
                    context = ConversationContext(
                        context_id=row["context_id"],
                        room_id=row["room_id"],
                        user_id=row["user_id"],
                        summary=row["summary"] or "",
                        key_topics=(
                            json.loads(row["key_topics"]) if row["key_topics"] else []
                        ),
                        sentiment=row["sentiment"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )

                    # Redis에 캐시
                    if redis_client:
                        await redis_client.setex(
                            cache_key, 300, json.dumps(context.model_dump())
                        )

                    return context
        except Exception as e:
            logger.error(f"Failed to get context: {e}")

        return None

    async def update_context(self, context_update: ContextUpdate) -> bool:
        """대화 맥락 업데이트"""
        try:
            current_time = get_current_timestamp()

            # 기존 맥락 조회 또는 새로 생성
            existing = await self.get_context(
                context_update.room_id, context_update.user_id
            )

            if existing:
                # 기존 맥락 업데이트
                summary = context_update.summary or existing.summary
                key_topics = context_update.key_topics or existing.key_topics
                sentiment = context_update.sentiment or existing.sentiment
                context_id = existing.context_id
            else:
                # 새 맥락 생성
                summary = context_update.summary or ""
                key_topics = context_update.key_topics or []
                sentiment = context_update.sentiment or "neutral"
                context_id = generate_id()

            # SQLite에 저장
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conversation_contexts
                    (context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        context_id,
                        context_update.room_id,
                        context_update.user_id,
                        summary,
                        json.dumps(key_topics),
                        sentiment,
                        existing.created_at if existing else current_time,
                        current_time,
                    ),
                )
                conn.commit()

            # Redis 캐시 무효화
            async with self.get_redis_client() as redis_client:
                if redis_client:
                    cache_key = (
                        f"context:{context_update.room_id}:{context_update.user_id}"
                    )
                    await redis_client.delete(cache_key)

            # 새 메모리 추가
            if context_update.new_memory:
                for key, value in context_update.new_memory.items():
                    await self.set_memory(
                        context_update.room_id, context_update.user_id, key, value
                    )

            return True
        except Exception as e:
            logger.error(f"Failed to update context: {e}")
            return False

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """사용자 프로필 조회"""
        try:
            # Redis에서 조회
            async with self.get_redis_client() as redis_client:
                if redis_client:
                    cache_key = f"profile:{user_id}"
                    cached = await redis_client.get(cache_key)
                    if cached:
                        data = json.loads(cached)
                        return UserProfile(**data)

            # SQLite에서 조회
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM user_profiles WHERE user_id = ?
                """,
                    (user_id,),
                )

                row = cursor.fetchone()
                if row:
                    profile = UserProfile(
                        user_id=row["user_id"],
                        name=row["name"],
                        preferences=(
                            json.loads(row["preferences"]) if row["preferences"] else {}
                        ),
                        conversation_style=row["conversation_style"],
                        interests=(
                            json.loads(row["interests"]) if row["interests"] else []
                        ),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )

                    # Redis에 캐시
                    if redis_client:
                        await redis_client.setex(
                            cache_key, 600, json.dumps(profile.model_dump())
                        )

                    return profile
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")

        return None

    async def update_user_profile(self, profile: UserProfile) -> bool:
        """사용자 프로필 업데이트"""
        try:
            current_time = get_current_timestamp()

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_profiles
                    (user_id, name, preferences, conversation_style, interests, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        profile.user_id,
                        profile.name,
                        json.dumps(profile.preferences),
                        profile.conversation_style,
                        json.dumps(profile.interests),
                        profile.created_at or current_time,
                        current_time,
                    ),
                )
                conn.commit()

            # Redis 캐시 무효화
            async with self.get_redis_client() as redis_client:
                if redis_client:
                    cache_key = f"profile:{profile.user_id}"
                    await redis_client.delete(cache_key)

            return True
        except Exception as e:
            logger.error(f"Failed to update user profile: {e}")
            return False

    async def set_memory(
        self,
        room_id: str,
        user_id: str,
        key: str,
        value: str,
        importance: float = 1.0,
        ttl: Optional[int] = None,
    ) -> bool:
        """메모리 설정"""
        try:
            memory_id = generate_id()
            current_time = get_current_timestamp()
            expires_at = current_time + ttl if ttl else None

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_entries
                    (memory_id, room_id, user_id, memory_key, memory_value, importance, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        memory_id,
                        room_id,
                        user_id,
                        key,
                        value,
                        importance,
                        expires_at,
                        current_time,
                    ),
                )
                conn.commit()

            # Redis에도 저장 (빠른 접근용)
            async with self.get_redis_client() as redis_client:
                if redis_client:
                    cache_key = f"memory:{room_id}:{user_id}:{key}"
                    if ttl:
                        await redis_client.setex(cache_key, ttl, value)
                    else:
                        await redis_client.set(cache_key, value)

            return True
        except Exception as e:
            logger.error(f"Failed to set memory: {e}")
            return False

    async def get_memory(self, room_id: str, user_id: str, key: str) -> Optional[str]:
        """메모리 조회"""
        try:
            # Redis에서 먼저 조회
            async with self.get_redis_client() as redis_client:
                if redis_client:
                    cache_key = f"memory:{room_id}:{user_id}:{key}"
                    value = await redis_client.get(cache_key)
                    if value:
                        return value.decode("utf-8")

            # SQLite에서 조회
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT memory_value FROM memory_entries
                    WHERE room_id = ? AND user_id = ? AND memory_key = ?
                    AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY importance DESC, created_at DESC
                    LIMIT 1
                """,
                    (room_id, user_id, key, get_current_timestamp()),
                )

                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logger.error(f"Failed to get memory: {e}")

        return None

    async def get_relevant_memories(
        self, room_id: str, user_id: str, query: str, limit: int = 5
    ) -> List[MemoryEntry]:
        """관련 메모리 조회 (간단한 키워드 매칭)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM memory_entries
                    WHERE room_id = ? AND user_id = ?
                    AND (expires_at IS NULL OR expires_at > ?)
                    AND (memory_key LIKE ? OR memory_value LIKE ?)
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """,
                    (
                        room_id,
                        user_id,
                        get_current_timestamp(),
                        f"%{query}%",
                        f"%{query}%",
                        limit,
                    ),
                )

                memories: List[MemoryEntry] = []
                for row in cursor.fetchall():
                    memory = MemoryEntry(
                        memory_id=row["memory_id"],
                        room_id=row["room_id"],
                        user_id=row["user_id"],
                        key=row["memory_key"],
                        value=row["memory_value"],
                        importance=row["importance"],
                        expires_at=row["expires_at"],
                        created_at=row["created_at"],
                    )
                    memories.append(memory)

                return memories
        except Exception as e:
            logger.error(f"Failed to get relevant memories: {e}")
            return []

    async def cleanup_expired_memories(self) -> int:
        """만료된 메모리 정리"""
        try:
            current_time = get_current_timestamp()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM memory_entries
                    WHERE expires_at IS NOT NULL AND expires_at <= ?
                """,
                    (current_time,),
                )

                deleted_count = cursor.rowcount
                conn.commit()

                logger.info(f"Cleaned up {deleted_count} expired memories")
                return deleted_count
        except Exception as e:
            logger.error(f"Failed to cleanup expired memories: {e}")
            return 0


