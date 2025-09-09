"""
Hybrid Search Service - Common search logic for RAG and Memory services.
Provides unified hybrid search functionality combining BM25, vector similarity, and time decay.
"""
import logging
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from abc import ABC, abstractmethod

from app.config.settings import settings

logger = logging.getLogger(__name__)


class SearchResult(ABC):
    """Abstract base class for search results."""
    pass


class MessageSearchResult:
    """Search result for message-based searches."""
    def __init__(self, message_id: str, content: str, score: float, timestamp: Optional[datetime] = None, **kwargs):
        self.message_id = message_id
        self.content = content
        self.score = score
        self.timestamp = timestamp
        self.metadata = kwargs


class ChunkSearchResult:
    """Search result for chunk-based searches."""
    def __init__(self, chunk_id: str, chunk_text: str, score: float, **kwargs):
        self.chunk_id = chunk_id
        self.chunk_text = chunk_text
        self.score = score
        self.metadata = kwargs


class HybridSearchService:
    """
    Unified hybrid search service that provides common search functionality
    for both RAG and Memory services.
    """
    
    def __init__(self):
        self.bm25_weight = getattr(settings, 'RAG_BM25_WEIGHT', 0.3)
        self.vector_weight = getattr(settings, 'RAG_VEC_WEIGHT', 0.7)
        self.time_decay_lambda = getattr(settings, 'TIME_DECAY_LAMBDA', 0.1)
        self.rag_time_decay = getattr(settings, 'RAG_TIME_DECAY', 0.05)
    
    def normalize_scores(self, scores: List[float]) -> List[float]:
        """
        Normalize scores to 0-1 range using min-max normalization.
        
        Args:
            scores: List of raw scores to normalize
            
        Returns:
            List of normalized scores in 0-1 range
        """
        if not scores:
            return []
        
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        return [(score - min_score) / (max_score - min_score) for score in scores]
    
    def normalize_result_scores(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize scores in result dictionaries.
        
        Args:
            results: List of result dictionaries with 'score' key
            
        Returns:
            List of results with normalized scores
        """
        if not results:
            return []
        
        scores = [r.get('score', 0) for r in results]
        normalized_scores = self.normalize_scores(scores)
        
        for i, result in enumerate(results):
            result['score'] = normalized_scores[i]
        
        return results
    
    def apply_time_decay_exponential(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply exponential time decay to search results.
        Uses: score * exp(-lambda * age_days)
        
        Args:
            results: List of result dictionaries with 'timestamp' and 'score' keys
            
        Returns:
            List of results with time-decayed scores
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        
        for result in results:
            timestamp = result.get('timestamp')
            if not timestamp:
                # Default decay for results with no timestamp
                result['score'] *= 0.5
                continue
            
            # Convert timestamp to seconds if it's a datetime object
            if hasattr(timestamp, 'timestamp'):
                timestamp_ts = timestamp.timestamp()
            else:
                timestamp_ts = timestamp
            
            age_seconds = now_ts - timestamp_ts
            age_days = age_seconds / (60 * 60 * 24)
            decay_factor = math.exp(-self.time_decay_lambda * age_days)
            result['score'] *= decay_factor
        
        return results
    
    def apply_time_decay_linear(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply linear time decay to search results.
        Uses: score / (1 + decay_factor * days_old)
        
        Args:
            results: List of result dictionaries with 'created_at' and 'score' keys
            
        Returns:
            List of results with time-decayed scores
        """
        now = datetime.now(timezone.utc)
        
        for result in results:
            created_at = result.get('created_at')
            if not created_at:
                # Default decay for results with no timestamp
                result['score'] *= 0.5
                continue
            
            # Ensure timezone awareness
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            days_old = (now - created_at).total_seconds() / (3600 * 24)
            decay = 1 / (1 + self.rag_time_decay * days_old)
            result['score'] *= decay
        
        return results
    
    def merge_search_results(
        self, 
        bm25_results: List[Dict[str, Any]], 
        vector_results: List[Dict[str, Any]],
        result_id_key: str = 'message_id'
    ) -> List[Dict[str, Any]]:
        """
        Merge BM25 and vector search results with weighted scoring.
        
        Args:
            bm25_results: List of BM25 search results
            vector_results: List of vector search results
            result_id_key: Key to use for identifying unique results
            
        Returns:
            List of merged and scored results
        """
        merged = {}
        
        # Normalize scores before merging
        norm_bm25 = self.normalize_result_scores(bm25_results)
        norm_vector = self.normalize_result_scores(vector_results)
        
        # Add BM25 results with weight
        for result in norm_bm25:
            result_id = result.get(result_id_key)
            if result_id:
                merged[result_id] = result.copy()
                merged[result_id]['score'] *= self.bm25_weight
        
        # Add vector results with weight
        for result in norm_vector:
            result_id = result.get(result_id_key)
            if result_id:
                if result_id in merged:
                    merged[result_id]['score'] += result['score'] * self.vector_weight
                else:
                    merged[result_id] = result.copy()
                    merged[result_id]['score'] *= self.vector_weight
        
        # Sort by combined score
        return sorted(list(merged.values()), key=lambda x: x['score'], reverse=True)
    
    def combine_scores_with_weights(
        self, 
        bm25_scores: List[float], 
        vector_scores: List[float]
    ) -> List[float]:
        """
        Combine BM25 and vector scores with configurable weights.
        
        Args:
            bm25_scores: List of BM25 scores
            vector_scores: List of vector similarity scores
            
        Returns:
            List of combined scores
        """
        if len(bm25_scores) != len(vector_scores):
            raise ValueError("BM25 and vector scores must have the same length")
        
        # Normalize both score sets
        norm_bm25 = self.normalize_scores(bm25_scores)
        norm_vector = self.normalize_scores(vector_scores)
        
        # Combine with weights
        combined_scores = []
        for i in range(len(norm_bm25)):
            combined_score = (self.bm25_weight * norm_bm25[i] + 
                            self.vector_weight * norm_vector[i])
            combined_scores.append(combined_score)
        
        return combined_scores
    
    def format_search_results(
        self, 
        results: List[Dict[str, Any]], 
        result_type: str = "message",
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Format search results into a consistent structure.
        
        Args:
            results: List of search results
            result_type: Type of results ("message" or "chunk")
            include_metadata: Whether to include metadata fields
            
        Returns:
            List of formatted results
        """
        formatted_results = []
        
        for result in results:
            if result_type == "message":
                formatted_result = {
                    "id": result.get("id", result.get("message_id")),
                    "thread_id": result.get("thread_id"),
                    "content": result.get("content"),
                    "role": result.get("role", "message"),
                    "created_at": result.get("created_at"),
                    "source": "message",
                    "score": result.get("score", 0),
                }
            elif result_type == "chunk":
                formatted_result = {
                    "id": f"attachment_{result.get('chunk', {}).get('id', result.get('chunk_id'))}",
                    "thread_id": result.get("thread_id"),
                    "content": result.get("chunk", {}).get("chunk_text", result.get("chunk_text")),
                    "role": "attachment",
                    "created_at": None,
                    "source": "attachment",
                    "score": result.get("score", 0),
                }
            else:
                # Generic format
                formatted_result = {
                    "id": result.get("id"),
                    "content": result.get("content"),
                    "score": result.get("score", 0),
                }
            
            if include_metadata and "metadata" in result:
                formatted_result.update(result["metadata"])
            
            formatted_results.append(formatted_result)
        
        return formatted_results
    
    def get_final_ranked_results(
        self, 
        all_results: List[Dict[str, Any]], 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get final ranked results with normalized relevance scores.
        
        Args:
            all_results: List of all search results
            limit: Maximum number of results to return
            
        Returns:
            List of top results with relevance scores
        """
        if not all_results:
            return []
        
        # Normalize scores across all results
        all_scores = [res.get("score", 0) for res in all_results]
        normalized_scores = self.normalize_scores(all_scores)
        
        # Update results with normalized scores
        for i, result in enumerate(all_results):
            result["relevance_score"] = normalized_scores[i]
            # Keep original score for debugging if needed
            if "score" in result:
                result["original_score"] = result["score"]
        
        # Sort by relevance score and return top results
        all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return all_results[:limit]


# Global service instance
hybrid_search_service: "HybridSearchService" = None

def get_hybrid_search_service() -> "HybridSearchService":
    """Get the global HybridSearchService instance."""
    global hybrid_search_service
    if hybrid_search_service is None:
        hybrid_search_service = HybridSearchService()
    return hybrid_search_service
