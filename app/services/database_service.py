import psycopg2
import logging
from typing import Optional, List, Dict, Any
from app.config.settings import settings
from pgvector.psycopg2 import register_vector

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self):
        self.conn = None

    def get_connection(self):
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(settings.DATABASE_URL)
                register_vector(self.conn)
                logger.info("Database connection successful")
            except psycopg2.OperationalError as e:
                logger.error(f"Database connection failed: {e}")
                raise
        return self.conn

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
                return []

    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        conn = self.get_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
            return cur.rowcount

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()
            logger.info("Database connection closed")

# Singleton instance, lazily initialized
_database_service_instance = None

def get_database_service():
    """Returns the singleton instance of the DatabaseService."""
    global _database_service_instance
    if _database_service_instance is None:
        _database_service_instance = DatabaseService()
    return _database_service_instance
