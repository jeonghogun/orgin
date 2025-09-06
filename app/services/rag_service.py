import asyncio
import json
import logging
from typing import List, Optional, Dict, Any

import openai
from app.config.settings import settings
from app.services.database_service import DatabaseService, get_database_service
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self):
        self.db: DatabaseService = get_database_service()
        self.openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def create_and_store_chunks(self, attachment_id: str, text_chunks: List[str]):
        if not text_chunks:
            return
        try:
            response = await self.openai_client.embeddings.create(input=text_chunks, model="text-embedding-3-small")
            embeddings = [item.embedding for item in response.data]

            # This is inefficient but simple. A real implementation should use batch inserts.
            for i, chunk_text in enumerate(text_chunks):
                chunk_id = f"cnk_{generate_id()}"
                query = "INSERT INTO attachment_chunks (id, attachment_id, chunk_text, embedding) VALUES (%s, %s, %s, %s)"
                params = (chunk_id, attachment_id, chunk_text, embeddings[i])
                self.db.execute_update(query, params)
            logger.info(f"Stored {len(text_chunks)} chunks for attachment {attachment_id}.")
        except Exception as e:
            logger.error(f"Failed to store chunks for attachment {attachment_id}: {e}", exc_info=True)
            raise

    async def get_context_from_attachments(self, query: str, thread_id: str, top_k: int = 3) -> str:
        try:
            response = await self.openai_client.embeddings.create(input=[query], model="text-embedding-3-small")
            query_embedding = response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to get embedding for RAG query: {e}")
            return ""

        # This query is complex. It finds all messages in a thread, unnests the attachment IDs
        # from the meta field, and then finds chunks related to those attachments.
        # NOTE: This uses jsonb_array_elements_text which is specific to PostgreSQL.
        sql_query = """
            WITH thread_attachments AS (
                SELECT DISTINCT jsonb_array_elements_text(meta->'attachments') AS attachment_id
                FROM conversation_messages
                WHERE thread_id = %s AND meta->'attachments' IS NOT NULL
            )
            SELECT ac.chunk_text, ac.embedding <=> %s AS distance
            FROM attachment_chunks ac
            JOIN thread_attachments ta ON ac.attachment_id = ta.attachment_id
            ORDER BY distance
            LIMIT %s
        """
        params = (thread_id, query_embedding, top_k)
        
        try:
            results = self.db.execute_query(sql_query, params)
            if not results:
                return ""
            
            context_str = "\n---\n".join([row["chunk_text"] for row in results])
            return f"--- Retrieved Context from Files ---\n{context_str}\n--- End of Context ---"
        except Exception as e:
            logger.error(f"Failed to retrieve context for thread {thread_id}: {e}")
            return ""

# Global service instance
rag_service: "RAGService" = None

def get_rag_service() -> "RAGService":
    global rag_service
    if rag_service is None:
        rag_service = RAGService()
    return rag_service
