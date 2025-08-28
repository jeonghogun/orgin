"""
Memory Service - Manages long-term memories using PostgreSQL and pgvector.
"""
import logging
import json
from typing import List, Optional, Tuple

from app.models.memory_schemas import MemoryEntry, UserProfile, ConversationContext, ContextUpdate
from app.services.database_service import DatabaseService
from app.services.llm_service import LLMService
from app.utils.helpers import generate_id, get_current_timestamp

logger = logging.getLogger(__name__)

class MemoryService:
    """
    Manages the creation, retrieval, and semantic search of memories,
    all stored within the primary PostgreSQL database.
    """

    def __init__(self, db_service: DatabaseService, llm_service: LLMService):
        """
        Initializes the MemoryService with dependencies.
        """
        super().__init__()
        self.db = db_service
        self.llm_service = llm_service

    async def set_memory(
        self,
        room_id: str,
        user_id: str,
        key: str,
        value: str,
        importance: float = 1.0,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Creates an embedding for the memory's value and saves it to the database.
        """
        try:
            memory_id = generate_id()
            current_time = get_current_timestamp()
            expires_at = current_time + ttl if ttl else None

            # Generate an embedding for the memory's value for semantic search
            embedding, _ = await self.llm_service.generate_embedding(value)

            query = """
                INSERT INTO memories (memory_id, user_id, room_id, key, value, embedding, importance, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                memory_id,
                user_id,
                room_id,
                key,
                value,
                embedding,
                importance,
                expires_at,
                current_time,
            )
            self.db.execute_update(query, params)
            logger.info(f"Successfully saved memory '{key}' for user '{user_id}' in room '{room_id}'.")
            return True
        except Exception as e:
            logger.error(f"Failed to set memory for user '{user_id}': {e}", exc_info=True)
            return False

    async def get_memory(self, room_id: str, user_id: str, key: str) -> Optional[MemoryEntry]:
        """
        Retrieves a specific memory by its key for a given user and room.
        """
        query = """
            SELECT * FROM memories
            WHERE user_id = %s AND room_id = %s AND key = %s
            AND (expires_at IS NULL OR expires_at > %s)
            ORDER BY created_at DESC
            LIMIT 1
        """
        params = (user_id, room_id, key, get_current_timestamp())
        result = self.db.execute_query(query, params)
        return MemoryEntry(**result[0]) if result else None

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """
        Retrieves and decrypts a user's profile from the database.
        If no profile exists, it creates a new one with encrypted fields.
        """
        from app.config.settings import settings
        key = settings.DB_ENCRYPTION_KEY

        try:
            query = """
                SELECT
                    user_id,
                    role,
                    pgp_sym_decrypt(name, %s::text) as name,
                    pgp_sym_decrypt(preferences, %s::text) as preferences,
                    conversation_style,
                    interests,
                    created_at,
                    updated_at
                FROM user_profiles WHERE user_id = %s
            """
            params = (key, key, user_id)
            results = self.db.execute_query(query, params)

            if results:
                profile_data = results[0]
                # Decrypted preferences will be a string, so we need to parse it
                if profile_data['preferences']:
                    profile_data['preferences'] = json.loads(profile_data['preferences'])
                else:
                    profile_data['preferences'] = {} # Default to empty dict if NULL

                if not profile_data['interests']:
                    profile_data['interests'] = [] # Default to empty list if NULL

                return UserProfile(**profile_data)

            # If no profile, create a default one
            logger.info(f"No profile found for user '{user_id}'. Creating a default one.")
            new_profile = UserProfile(
                user_id=user_id,
                created_at=get_current_timestamp(),
                updated_at=get_current_timestamp()
            )

            # Save the new profile to the DB with encrypted fields
            insert_query = """
                INSERT INTO user_profiles (user_id, role, name, preferences, conversation_style, interests, created_at, updated_at)
                VALUES (%s, %s, pgp_sym_encrypt(%s, %s::text), pgp_sym_encrypt(%s, %s::text), %s, %s, %s, %s)
            """
            insert_params = (
                new_profile.user_id,
                new_profile.role,
                new_profile.name if new_profile.name is not None else None, key,
                json.dumps(new_profile.preferences), key,
                new_profile.conversation_style,
                new_profile.interests,
                new_profile.created_at,
                new_profile.updated_at
            )
            self.db.execute_update(insert_query, insert_params)
            return new_profile
        except Exception as e:
            logger.error(f"Failed to get or create user profile for '{user_id}': {e}", exc_info=True)
            return None

    async def get_context(self, room_id: str, user_id: str) -> Optional[ConversationContext]:
        """
        Retrieves the conversation context for a given room and user.
        """
        try:
            query = "SELECT * FROM conversation_contexts WHERE room_id = %s AND user_id = %s"
            params = (room_id, user_id)
            results = self.db.execute_query(query, params)
            if results:
                return ConversationContext(**results[0])
            return None # No context found
        except Exception as e:
            logger.error(f"Failed to get context for room '{room_id}': {e}", exc_info=True)
            return None

    async def update_context(self, context_update: ContextUpdate) -> bool:
        """
        Updates or creates a conversation context.
        """
        try:
            current_time = get_current_timestamp()
            # Use ON CONFLICT to handle both INSERT and UPDATE
            query = """
                INSERT INTO conversation_contexts (context_id, room_id, user_id, summary, key_topics, sentiment, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (room_id, user_id) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    key_topics = EXCLUDED.key_topics,
                    sentiment = EXCLUDED.sentiment,
                    updated_at = EXCLUDED.updated_at
            """
            params = (
                generate_id("context"),
                context_update.room_id,
                context_update.user_id,
                context_update.summary,
                context_update.key_topics,
                context_update.sentiment,
                current_time,
                current_time
            )
            self.db.execute_update(query, params)
            return True
        except Exception as e:
            logger.error(f"Failed to update context for room '{context_update.room_id}': {e}", exc_info=True)
            return False

    async def get_relevant_memories(
        self,
        room_ids: List[str],
        user_id: str,
        query_text: str,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        Finds the most relevant memories across a list of room IDs for a user,
        based on semantic similarity of the query text.
        """
        try:
            # Generate an embedding for the search query
            query_embedding, _ = await self.llm_service.generate_embedding(query_text)

            # The query uses the L2 distance operator (<->) from pgvector to find the closest matches.
            # It searches across all specified room_ids.
            query = """
                SELECT *, (embedding <=> %s) AS distance FROM memories
                WHERE user_id = %s AND room_id = ANY(%s)
                AND (expires_at IS NULL OR expires_at > %s)
                ORDER BY distance ASC
                LIMIT %s
            """
            params = (query_embedding, user_id, room_ids, get_current_timestamp(), limit)

            results = self.db.execute_query(query, params)

            memories = [MemoryEntry(**row) for row in results]
            logger.info(f"Found {len(memories)} relevant memories for user '{user_id}' across rooms {room_ids}.")
            return memories
        except Exception as e:
            logger.error(f"Failed to get relevant memories for user '{user_id}': {e}", exc_info=True)
            return []

    async def cleanup_expired_memories(self) -> int:
        """
        Removes all expired memories from the database.
        Returns the number of memories deleted.
        """
        try:
            current_time = get_current_timestamp()
            query = "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= %s"
            params = (current_time,)
            deleted_count = self.db.execute_update(query, params)
            logger.info(f"Cleaned up {deleted_count} expired memories.")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to cleanup expired memories: {e}")
            return 0
