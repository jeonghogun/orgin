# Hybrid Search Guide

This document provides an overview of the hybrid search functionality implemented in the Origin Project.

## 1. Overview

The global search feature (accessible via Cmd+K) uses a sophisticated hybrid search algorithm to provide the most relevant results from a user's conversation history and attached documents. It combines three techniques:

1.  **BM25 (Keyword Search):** A powerful, traditional keyword-based search algorithm that excels at matching explicit terms and queries.
2.  **Vector Search (Semantic Search):** A modern, AI-based search that finds results based on semantic meaning and context, not just keywords. This is powered by text embeddings.
3.  **Time Decay:** A weighting system that gives more importance to recent messages, ensuring that the most current information is prioritized.

The scores from these three systems are combined to produce a final, highly relevant ranking.

## 2. API Endpoint

The hybrid search functionality is exposed via the following API endpoint:

`GET /api/search/hybrid`

### Query Parameters:
-   `q` (string, required): The search query.
-   `thread_id` (string, optional): The ID of a specific conversation thread to search within. If not provided, the search will be performed across all threads accessible by the user.
-   `limit` (integer, optional, default: 10): The maximum number of results to return.

### Example Usage:
```
GET /api/search/hybrid?q=AI%20ethics&thread_id=thread_abc123&limit=5
```

## 3. Backend Implementation

The core logic resides in `app/services/rag_service.py` within the `search_hybrid` method.

-   It fetches messages and attachment chunks in parallel.
-   It calculates BM25 scores for keyword relevance.
-   It calculates vector similarity scores for semantic relevance.
-   It applies a time-decay penalty to older messages.
-   It uses the `HybridSearchService` to combine these scores into a final ranking.
-   The final ranked list of results is returned.
