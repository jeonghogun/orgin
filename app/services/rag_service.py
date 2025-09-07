import asyncio
import json
import logging
import math
from typing import List, Optional, Dict, Any, Tuple

import openai
from rank_bm25 import BM25Okapi
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
        """
        Hybrid RAG search combining BM25 keyword search and vector similarity search.
        """
        try:
            # Get all text chunks for the thread
            chunks_data = self._get_thread_chunks(thread_id)
            if not chunks_data:
                return ""

            # Perform hybrid search
            hybrid_results = await self._hybrid_search(query, chunks_data, top_k)
            if not hybrid_results:
                return ""

            context_str = "\n---\n".join([result["chunk_text"] for result in hybrid_results])
            return f"--- Retrieved Context from Files ---\n{context_str}\n--- End of Context ---"
        except Exception as e:
            logger.error(f"Failed to retrieve context for thread {thread_id}: {e}")
            return ""

    def _get_thread_chunks(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all text chunks for a thread with their embeddings."""
        sql_query = """
            WITH thread_attachments AS (
                SELECT DISTINCT jsonb_array_elements_text(meta->'attachments') AS attachment_id
                FROM messages
                WHERE room_id = %s AND meta->'attachments' IS NOT NULL
            )
            SELECT ac.id, ac.chunk_text, ac.embedding
            FROM attachment_chunks ac
            JOIN thread_attachments ta ON ac.attachment_id = ta.attachment_id
        """
        params = (thread_id,)

        try:
            results = self.db.execute_query(sql_query, params)
            return results
        except Exception as e:
            logger.error(f"Failed to get thread chunks: {e}")
            return []

    async def _hybrid_search(self, query: str, chunks_data: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """Perform hybrid search combining BM25 and vector similarity."""
        if not chunks_data:
            return []

        # Prepare data for BM25
        chunk_texts = [chunk["chunk_text"] for chunk in chunks_data]
        chunk_ids = [chunk["id"] for chunk in chunks_data]
        
        # Tokenize for BM25 (simple whitespace tokenization)
        tokenized_corpus = [text.lower().split() for text in chunk_texts]
        bm25 = BM25Okapi(tokenized_corpus)
        
        # Get BM25 scores
        query_tokens = query.lower().split()
        bm25_scores = bm25.get_scores(query_tokens)
        
        # Get vector similarity scores
        vector_scores = await self._get_vector_scores(query, chunks_data)
        
        # Normalize scores
        bm25_scores_norm = self._normalize_scores(bm25_scores)
        vector_scores_norm = self._normalize_scores(vector_scores)
        
        # Combine scores with weights
        bm25_weight = getattr(settings, 'RAG_BM25_WEIGHT', 0.3)
        vector_weight = getattr(settings, 'RAG_VEC_WEIGHT', 0.7)
        
        combined_scores = []
        for i, chunk in enumerate(chunks_data):
            combined_score = (bm25_weight * bm25_scores_norm[i] + 
                            vector_weight * vector_scores_norm[i])
            combined_scores.append({
                'chunk': chunk,
                'score': combined_score,
                'bm25_score': bm25_scores_norm[i],
                'vector_score': vector_scores_norm[i]
            })
        
        # Sort by combined score and return top_k
        combined_scores.sort(key=lambda x: x['score'], reverse=True)
        return [item['chunk'] for item in combined_scores[:top_k]]

    async def _get_vector_scores(self, query: str, chunks_data: List[Dict[str, Any]]) -> List[float]:
        """Get vector similarity scores for the query against chunks."""
        try:
            # Get query embedding
            response = await self.openai_client.embeddings.create(
                input=[query], 
                model="text-embedding-3-small"
            )
            query_embedding = response.data[0].embedding
            
            # Calculate cosine similarity for each chunk
            scores = []
            for chunk in chunks_data:
                chunk_embedding = chunk["embedding"]
                similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                scores.append(similarity)
            
            return scores
        except Exception as e:
            logger.error(f"Failed to get vector scores: {e}")
            return [0.0] * len(chunks_data)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Normalize scores to 0-1 range using min-max normalization."""
        if not scores:
            return []
        
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        return [(score - min_score) / (max_score - min_score) for score in scores]

    async def generate_rag_response(
        self, 
        room_id: str, 
        user_id: str, 
        user_message: str, 
        attachments: Optional[List[str]], 
        memory_context: List[Dict[str, Any]], 
        message_id: str
    ) -> str:
        """
        Generate AI response using RAG context and LLM.
        """
        try:
            # Get RAG context from attachments
            rag_context = await self.get_context_from_attachments(user_message, room_id)
            
            # Build prompt with context
            prompt_parts = []
            
            if rag_context:
                prompt_parts.append(f"Context from documents:\n{rag_context}")
            
            if memory_context:
                memory_text = "\n".join([f"- {item.get('content', '')}" for item in memory_context])
                prompt_parts.append(f"Relevant memories:\n{memory_text}")
            
            prompt_parts.append(f"User message: {user_message}")
            
            system_prompt = """You are a helpful AI assistant. Use the provided context and memories to give accurate, helpful responses. If the context doesn't contain relevant information, say so clearly."""
            
            user_prompt = "\n\n".join(prompt_parts)
            
            # Generate response using OpenAI
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Failed to generate RAG response: {e}")
            return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

# Global service instance
rag_service: "RAGService" = None

def get_rag_service() -> "RAGService":
    global rag_service
    if rag_service is None:
        rag_service = RAGService()
    return rag_service
