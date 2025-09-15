import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

import openai
from rank_bm25 import BM25Okapi
from app.config.settings import settings
from app.services.database_service import DatabaseService, get_database_service
from app.services.hybrid_search_service import get_hybrid_search_service
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self):
        self.db: DatabaseService = get_database_service()
        self.openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.hybrid_search = get_hybrid_search_service()

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
        # This query joins through messages and attachments to find all chunks
        # associated with a particular conversation thread.
        # It assumes that attachments are linked to messages via the 'meta' JSONB field.
        sql = """
            SELECT ac.id, ac.attachment_id, ac.chunk_text, ac.embedding
            FROM attachment_chunks ac
            JOIN attachments a ON ac.attachment_id = a.id
            JOIN conversation_messages cm ON a.id = (cm.meta->>'attachment_id')::text
            WHERE cm.thread_id = %s;
        """
        params = (thread_id,)
        try:
            return self.db.execute_query(sql, params)
        except Exception as e:
            # This might fail if the meta field is not used as expected, which is fine.
            logger.warning(f"Could not retrieve attachment chunks for thread {thread_id}, possibly due to schema mismatch or no attachments. Error: {e}")
            return []

    async def _hybrid_search(self, query: str, chunks_data: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """Perform hybrid search combining BM25 and vector similarity."""
        if not chunks_data:
            return []

        # Prepare data for BM25
        chunk_texts = [chunk["chunk_text"] for chunk in chunks_data]
        
        # Tokenize for BM25 (simple whitespace tokenization)
        tokenized_corpus = [text.lower().split() for text in chunk_texts]
        bm25 = BM25Okapi(tokenized_corpus)
        
        # Get BM25 scores
        query_tokens = query.lower().split()
        bm25_scores = bm25.get_scores(query_tokens)
        
        # Get vector similarity scores
        vector_scores = await self._get_vector_scores(query, chunks_data)
        
        # Use HybridSearchService to combine scores
        combined_scores = self.hybrid_search.combine_scores_with_weights(bm25_scores, vector_scores)
        
        # Format results
        results = []
        for i, chunk in enumerate(chunks_data):
            results.append({
                'chunk': chunk,
                'score': combined_scores[i],
                'bm25_score': bm25_scores[i],
                'vector_score': vector_scores[i]
            })
        
        # Sort by combined score and return top_k
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

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


    async def _get_rag_prompt_and_context(self, user_message: str, room_id: str, memory_context: List[Dict[str, Any]]) -> Tuple[str, str]:
        """Helper to build the RAG prompt and return the context string."""
        rag_context = await self.get_context_from_attachments(user_message, room_id)

        prompt_parts = []
        if rag_context:
            prompt_parts.append(f"Context from documents:\n{rag_context}")

        if memory_context:
            memory_text = "\n".join([f"- {item.get('content', '')}" for item in memory_context])
            prompt_parts.append(f"Relevant memories:\n{memory_text}")

        prompt_parts.append(f"User message: {user_message}")

        system_prompt = """You are a helpful AI assistant. Use the provided context and memories to give accurate, helpful responses. If the context doesn't contain relevant information, say so clearly."""
        user_prompt = "\n\n".join(prompt_parts)

        return system_prompt, user_prompt

    async def generate_rag_response(
        self, room_id: str, user_id: str, user_message: str,
        memory_context: List[Dict[str, Any]], message_id: str
    ) -> str:
        """Generates a standard, non-streaming RAG response."""
        try:
            system_prompt, user_prompt = await self._get_rag_prompt_and_context(user_message, room_id, memory_context)
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.7,
                stream=False,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Failed to generate RAG response: {e}")
            return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    async def generate_rag_response_stream(
        self, room_id: str, user_id: str, user_message: str,
        memory_context: List[Dict[str, Any]], message_id: str
    ):
        """Generates a streaming RAG response."""
        try:
            system_prompt, user_prompt = await self._get_rag_prompt_and_context(user_message, room_id, memory_context)

            stream = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.7,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"Failed to generate streaming RAG response: {e}")
            yield "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    async def search_hybrid(
        self, query: str, user_id: str, thread_id: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """
        Performs a hybrid search across conversation messages and attachments,
        combining BM25, vector similarity, and time decay.
        """
        # 1. Get messages and attachments from the database
        messages = self._get_thread_messages(thread_id) if thread_id else []
        attachment_chunks = self._get_thread_chunks(thread_id) if thread_id else []

        # 2. Search both sources in parallel
        message_results_task = asyncio.to_thread(self._bm25_search_with_time_decay, query, messages)
        attachment_results_task = self._hybrid_search(query, attachment_chunks, top_k=limit)

        message_results, attachment_results = await asyncio.gather(
            message_results_task, attachment_results_task
        )

        # 3. Format results into a common structure
        formatted_messages = [
            {
                "id": msg["id"],
                "thread_id": msg["thread_id"],
                "content": msg["content"],
                "role": msg["role"],
                "created_at": msg["created_at"].isoformat(),
                "source": "message",
                "score": score,
            }
            for msg, score in message_results
        ]

        formatted_attachments = [
            {
                "id": f"attachment_{res['chunk']['id']}",
                "thread_id": thread_id,
                "content": res["chunk"]["chunk_text"],
                "role": "attachment",
                "created_at": None,
                "source": "attachment",
                "score": res["score"],
            }
            for res in attachment_results
        ]

        all_results = formatted_messages + formatted_attachments
        if not all_results:
            return []

        # 4. Use HybridSearchService for final ranking
        final_results = self.hybrid_search.get_final_ranked_results(all_results, limit)
        return final_results

    def _get_thread_messages(
        self, thread_id: str
    ) -> List[Dict[str, Any]]:
        """Fetches all messages for a given thread from the database."""
        # Correctly fetches from conversation_messages table
        sql = """
            SELECT id, thread_id, content, role, created_at
            FROM conversation_messages
            WHERE thread_id = %s
            ORDER BY created_at ASC
        """
        params = (thread_id,)
        return self.db.execute_query(sql, params)

    def _bm25_search_with_time_decay(
        self, query: str, messages: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Performs BM25 search on messages and applies a time decay to the scores."""
        if not messages:
            return []

        corpus = [msg.get("content", "") for msg in messages]
        tokenized_corpus = [doc.lower().split() for doc in corpus]
        if not tokenized_corpus:
            return []

        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens = query.lower().split()
        bm25_scores = bm25.get_scores(query_tokens)

        # Prepare results for time decay
        results = []
        for i, msg in enumerate(messages):
            results.append({
                'message': msg,
                'score': bm25_scores[i],
                'created_at': msg.get("created_at")
            })

        # Apply time decay using HybridSearchService
        decayed_results = self.hybrid_search.apply_time_decay_linear(results)

        # Format as tuples
        final_results = []
        for result in decayed_results:
            final_results.append((result['message'], result['score']))

        return final_results


    def _build_rag_prompt(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Build RAG prompt with context chunks."""
        context_text = "\n\n".join([chunk.get('content', '') for chunk in context_chunks])
        
        prompt = f"""Based on the following context, please answer the user's question:

Context:
{context_text}

Question: {query}

Please provide a comprehensive answer based on the context provided."""
        
        return prompt


# Global service instance
rag_service: "RAGService" = None

def get_rag_service() -> "RAGService":
    global rag_service
    if rag_service is None:
        rag_service = RAGService()
    return rag_service
