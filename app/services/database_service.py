import psycopg2
import logging
from typing import Optional, List, Dict, Any
from app.config.settings import settings
from pgvector.psycopg2 import register_vector
import asyncio

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self):
        self.conn = None

    async def get_connection(self):
        if self.conn is None or self.conn.closed:
            try:
                self.conn = await asyncio.to_thread(psycopg2.connect, settings.DATABASE_URL)
                register_vector(self.conn)
                logger.info("Database connection successful")
            except psycopg2.OperationalError as e:
                logger.error(f"Database connection failed: {e}")
                raise
        return self.conn

    async def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        conn = await self.get_connection()
        with conn.cursor() as cur:
            await asyncio.to_thread(cur.execute, query, params)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in await asyncio.to_thread(cur.fetchall)]
            return []

    async def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        conn = await self.get_connection()
        with conn.cursor() as cur:
            await asyncio.to_thread(cur.execute, query, params)
            return cur.rowcount

    async def close(self):
        if self.conn and not self.conn.closed:
            await asyncio.to_thread(self.conn.close)
            logger.info("Database connection closed")

# Singleton instance, lazily initialized
_database_service_instance = None

def get_database_service():
    """Returns the singleton instance of the DatabaseService."""
    global _database_service_instance
    if _database_service_instance is None:
        _database_service_instance = DatabaseService()
    return _database_service_instance
