import psycopg2
import logging
from typing import Optional, List, Dict, Any, Tuple
from app.config.settings import settings
from pgvector.psycopg2 import register_vector # type: ignore
from psycopg2.extensions import connection

logger = logging.getLogger(__name__)


from app.core.secrets import SecretProvider

class DatabaseService:
    def __init__(self, secret_provider: SecretProvider) -> None:
        super().__init__()
        self.conn: Optional[connection] = None
        self.database_url = secret_provider.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL secret not found.")

    def get_connection(self) -> connection:
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(self.database_url)
                register_vector(self.conn)  # type: ignore
                logger.info("Database connection successful")
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
