import psycopg2
import logging
import time
import os
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from urllib.parse import urlparse, urlunparse
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extensions import connection, cursor as CursorClass

from app.core.secrets import SecretProvider
from app.models.schemas import Message
from app.utils.helpers import generate_id
from pgvector.psycopg2 import register_vector
from app.core.metrics import DB_QUERY_DURATION

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self, secret_provider: SecretProvider) -> None:
        super().__init__()
        
        # Check if we're in test mode first
        self._is_test_mode = os.getenv("PYTEST_CURRENT_TEST") is not None
        
        if self._is_test_mode:
            # In test mode, use environment variables directly
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable not found in test mode.")
            self.database_url = str(database_url)
            self.db_encryption_key = os.getenv("DB_ENCRYPTION_KEY", "test-encryption-key-32-bytes-long")
        else:
            # In production mode, use secret provider
            database_url = secret_provider.get("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL secret not found.")
            # Convert PostgresDsn to string if needed
            self.database_url = str(database_url)
            self.db_encryption_key = secret_provider.get("DB_ENCRYPTION_KEY")
            if not self.db_encryption_key:
                raise ValueError("DB_ENCRYPTION_KEY not found.")

        self._apply_test_overrides()
        
        self.pool: Optional[SimpleConnectionPool] = None

    def _apply_test_overrides(self) -> None:
        """Allow test-specific environment variables to override connection details."""

        override_host = os.getenv("TEST_DB_HOST")
        override_port = os.getenv("TEST_DB_PORT")

        if not override_host and not override_port:
            return

        parsed = urlparse(self.database_url)

        # Split userinfo and host/port sections of the netloc
        userinfo, at, hostport = parsed.netloc.rpartition("@")
        host, _, port = hostport.partition(":")

        new_host = override_host or host
        new_port = override_port or port

        # Reconstruct the netloc respecting available components
        host_segment = new_host or host
        if new_port:
            host_segment = f"{host_segment}:{new_port}"

        if at:
            netloc = f"{userinfo}@{host_segment}"
        else:
            netloc = host_segment

        self.database_url = urlunparse(parsed._replace(netloc=netloc))

    def _get_or_create_pool(self) -> SimpleConnectionPool:
        """Lazily creates and returns the connection pool."""
        if self.pool is None:
            try:
                self.pool = SimpleConnectionPool(
                    minconn=5,
                    maxconn=20,
                    dsn=self.database_url
                )
                logger.info("Database connection pool created successfully on first use.")
            except psycopg2.OperationalError as e:
                logger.error(f"Failed to create database connection pool: {e}")
                raise
        return self.pool

    def _clear_test_data(self, conn: connection) -> None:
        """Clear all test data when in test mode."""
        if not self._is_test_mode:
            return

        # Many integration tests seed prerequisite data (e.g. rooms) in their
        # fixtures before exercising the API.  Clearing the tables on every
        # new connection causes those fixtures to lose their setup.  Only run
        # the automatic cleanup when an explicit opt-in flag is provided so
        # tests can request a clean slate when they really need it.
        if os.getenv("PYTEST_RESET_DB_ON_CONNECT", "").lower() not in {"1", "true", "yes"}:
            return
            
        cursor = conn.cursor()
        try:
            # Clear tables in correct order to handle foreign key constraints
            tables = [
                "conversation_contexts", "review_events", "reviews", 
                "messages", "memories", "user_facts", "fact_store", 
                "rooms", "user_profiles"
            ]

            for table in tables:
                try:
                    cursor.execute(f"DELETE FROM {table};")
                except Exception as e:
                    # Table might not exist, skip it
                    logger.debug(f"Could not clear table {table}: {e}")
                    pass
            
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to clear test data: {e}")
            conn.rollback()
        finally:
            cursor.close()

    @contextmanager
    def get_connection(self) -> connection:
        """Get a connection from the lazily-initialized pool and register pgvector."""
        pool = self._get_or_create_pool()
        conn = pool.getconn()
        try:
            # Try to register vector extension, but don't fail if it's not available
            try:
                register_vector(conn)
            except psycopg2.ProgrammingError as e:
                if "vector type not found" in str(e):
                    logger.warning("pgvector extension not available, continuing without vector support")
                else:
                    raise
            # Clear test data if in test mode
            self._clear_test_data(conn)
            yield conn
        finally:
            pool.putconn(conn)

    @contextmanager
    def transaction(self, query_type: str = "unknown") -> CursorClass:
        """
        Provides a transactional cursor and records metrics.
        Commits if the block succeeds, rolls back if it fails.
        """
        start_time = time.time()
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    try:
                        yield cur
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        logger.error("Transaction failed, rolling back.", exc_info=True)
                        raise
        finally:
            duration = time.time() - start_time
            DB_QUERY_DURATION.labels(query_type=query_type).observe(duration)

    def execute_query(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a read-only query and fetch all results."""
        with self.transaction(query_type="read") as cur:
            cur.execute(query, params)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
            return []

    def execute_update(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> int:
        """Execute an update/insert/delete query and return the row count."""
        with self.transaction(query_type="write") as cur:
            cur.execute(query, params)
            return cur.rowcount

    def execute_returning(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a query that mutates data but also returns rows."""
        with self.transaction(query_type="write") as cur:
            cur.execute(query, params)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
            return []

    def get_messages_for_promotion(self, room_id: str) -> List[Message]:
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

    def copy_messages_to_room(self, messages: List[Message], new_room_id: str, user_id: str) -> int:
        """
        Copies a list of messages to a new room in a single transaction.
        """
        insert_query = """
            INSERT INTO messages (message_id, room_id, user_id, role, content, content_searchable, timestamp, embedding)
            VALUES (%s, %s, %s, %s, pgp_sym_encrypt(%s, %s), %s, %s, %s)
        """
        copied_count = 0
        try:
            with self.transaction(query_type="write") as cur:
                for message in messages:
                    new_message_id = generate_id()
                    author_id = message.user_id
                    params = (
                        new_message_id, new_room_id, author_id, message.role,
                        message.content, self.db_encryption_key, message.content, message.timestamp, None
                    )
                    cur.execute(insert_query, params)
                    copied_count += 1
        except Exception as e:
            logger.error(f"Failed to copy messages to room {new_room_id}: {e}")
            return 0

        return copied_count

    def close(self) -> None:
        """Close all connections in the pool."""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed.")

# Singleton instance, lazily initialized
_database_service_instance: Optional[DatabaseService] = None

def get_database_service() -> DatabaseService:
    """Returns the singleton instance of the DatabaseService."""
    from app.core.secrets import env_secrets_provider
    global _database_service_instance
    if _database_service_instance is None:
        _database_service_instance = DatabaseService(secret_provider=env_secrets_provider)
    return _database_service_instance
