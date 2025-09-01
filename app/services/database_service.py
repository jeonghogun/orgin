import psycopg2
import logging
from typing import Optional, List, Dict, Any, Tuple
from app.config.settings import settings
from pgvector.psycopg2 import register_vector # type: ignore
from psycopg2.extensions import connection

logger = logging.getLogger(__name__)


from app.core.secrets import SecretProvider

from app.models.schemas import Message
from app.utils.helpers import generate_id

class DatabaseService:
    def __init__(self, secret_provider: SecretProvider) -> None:
        super().__init__()
        self.conn: Optional[connection] = None
        self.database_url = secret_provider.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL secret not found.")
        self.db_encryption_key = secret_provider.get("DB_ENCRYPTION_KEY")
        if not self.db_encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY not found.")

    def get_connection(self) -> connection:
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(self.database_url)
                register_vector(self.conn)  # type: ignore
                logger.info("Database connection successful with vector support")
            except psycopg2.OperationalError as e:
                logger.error(f"Database connection failed: {e}")
                raise
        return self.conn

    def execute_query(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.description:
                    columns = [desc[0] for desc in cur.description]  # type: ignore
                    return [dict(zip(columns, row)) for row in cur.fetchall()]  # type: ignore
                return []

    def execute_update(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> int:
        conn = self.get_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
            return cur.rowcount

    async def get_messages_for_promotion(self, room_id: str) -> List[Message]:
        """Get and decrypt all messages for a room from the database."""
        query = """
            SELECT message_id, room_id, user_id, role,
                   pgp_sym_decrypt(content, %s) as content,
                   timestamp
            FROM messages
            WHERE room_id = %s
            ORDER BY timestamp ASC
        """
        params = (self.db_encryption_key, room_id)
        results = self.execute_query(query, params)
        return [Message(**row) for row in results]

    async def copy_messages_to_room(self, messages: List[Message], new_room_id: str, user_id: str) -> int:
        """Copies a list of messages to a new room, re-encrypting them."""
        copied_count = 0
        insert_query = """
            INSERT INTO messages (message_id, room_id, user_id, role, content, content_searchable, timestamp, embedding)
            VALUES (%s, %s, %s, %s, pgp_sym_encrypt(%s, %s), %s, %s, %s)
        """
        # Note: This is not the most performant way for bulk inserts,
        # but it's clear and sufficient for this feature.
        for message in messages:
            new_message_id = generate_id()
            # We preserve the original user_id of the message author
            author_id = message.user_id

            # Re-encrypt content with the key for the new insert
            params = (
                new_message_id, new_room_id, author_id, message.role,
                message.content, self.db_encryption_key, message.content, message.timestamp, None
            )
            try:
                self.execute_update(insert_query, params)
                copied_count += 1
            except Exception as e:
                logger.error(f"Failed to copy message {message.message_id} to room {new_room_id}: {e}")

        return copied_count

    def close(self) -> None:
        if self.conn and not self.conn.closed:
            self.conn.close()
            logger.info("Database connection closed")


# Singleton instance, lazily initialized
_database_service_instance: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Returns the singleton instance of the DatabaseService."""
    from app.core.secrets import env_secrets_provider
    global _database_service_instance
    if _database_service_instance is None:
        _database_service_instance = DatabaseService(secret_provider=env_secrets_provider)
    return _database_service_instance
