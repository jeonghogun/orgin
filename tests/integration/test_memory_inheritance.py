import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.api.dependencies import get_memory_service

# --- Test Data ---
USER_ID = "test-conftest-user"  # This must match the user_id from the authenticated_client fixture in conftest
MAIN_ROOM_MEMORY_VALUE = "The secret access phrase is 'blue-lorikeet-7'"
USER_QUERY = "What is the secret code?"
DISTRACTOR_MEMORY_VALUE = "The sky is often blue."

# Mock embeddings to simulate semantic similarity.
# The vectors must have 1536 dimensions to match the DB schema.
DIMENSIONS = 1536

# The query and the main room memory will have identical embeddings for perfect similarity
QUERY_EMBEDDING = [1.0] + [0.0] * (DIMENSIONS - 1)
MAIN_ROOM_MEMORY_EMBEDDING = [1.0] + [0.0] * (DIMENSIONS - 1)

# The distractor memory will have an orthogonal (dissimilar) embedding
DISTRACTOR_MEMORY_EMBEDDING = [0.0, 1.0] + [0.0] * (DIMENSIONS - 2)


@pytest.mark.asyncio
@patch("app.services.rag_service.RAGService._build_rag_prompt")
@patch.object(MemoryService, 'get_relevant_memories_hybrid', new_callable=AsyncMock)
@patch("app.api.dependencies.get_llm_service")
async def test_semantic_memory_inheritance(
    mock_get_llm,
    spied_get_relevant,
    mock_build_prompt,
    authenticated_client: TestClient,
    db_session,
):
    """
    Tests that a sub-room correctly inherits memories from its parent main room
    based on SEMANTIC similarity, not just keyword matching.
    """
    # --- 1. Configure Mocks ---

    # a) Configure the LLM service mock
    async def mock_generate_embedding(text: str):
        if text == USER_QUERY:
            return QUERY_EMBEDDING, {"total_tokens": 4}
        elif text == MAIN_ROOM_MEMORY_VALUE:
            return MAIN_ROOM_MEMORY_EMBEDDING, {"total_tokens": 8}
        return DISTRACTOR_MEMORY_EMBEDDING, {"total_tokens": 5}

    mock_llm_instance = MagicMock(spec=LLMService)
    mock_llm_instance.generate_embedding = AsyncMock(side_effect=mock_generate_embedding)
    mock_provider = AsyncMock()
    mock_provider.invoke.return_value = ('{"intent": "test_intent", "entities": {}}', {"total_tokens": 10})
    mock_llm_instance.get_provider.return_value = mock_provider
    mock_get_llm.return_value = mock_llm_instance

    # b) Configure the spy on MemoryService.get_relevant_memories
    from app.models.memory_schemas import MemoryEntry
    spied_get_relevant.return_value = [
        MemoryEntry(
            memory_id="mem_main", user_id=USER_ID, room_id="main_room_id_placeholder",
            key="secret", value=MAIN_ROOM_MEMORY_VALUE, created_at=12345, distance=0.0
        )
    ]

    # c) Configure the prompt builder mock
    mock_build_prompt.return_value = "Final Prompt"

    # --- 2. Setup: Create main and sub rooms ---
    client = authenticated_client
    main_room_res = client.post("/api/rooms", json={"name": "Main Inheritance Test", "type": "main"})
    assert main_room_res.status_code == 200, main_room_res.text
    main_room_id = main_room_res.json()["room_id"]
    spied_get_relevant.return_value[0].room_id = main_room_id # Update placeholder

    sub_room_res = client.post("/api/rooms", json={"name": "Sub Inheritance Test", "type": "sub", "parent_id": main_room_id})
    assert sub_room_res.status_code == 200, sub_room_res.text
    sub_room_id = sub_room_res.json()["room_id"]

    # --- 3. Add memories via API ---
    client.post("/api/memory", json={"room_id": main_room_id, "key": "secret", "value": MAIN_ROOM_MEMORY_VALUE})
    client.post("/api/memory", json={"room_id": sub_room_id, "key": "distractor", "value": DISTRACTOR_MEMORY_VALUE})

    # --- 4. Send a message to the SUB room ---
    rag_res = client.post("/api/rag/query", json={"room_id": sub_room_id, "query": USER_QUERY})
    assert rag_res.status_code == 200, rag_res.text

    # --- 5. Assertions ---
    spied_get_relevant.assert_called_once()
    call_kwargs = spied_get_relevant.call_args.kwargs
    assert set(call_kwargs["room_ids"]) == {main_room_id, sub_room_id}
    assert call_kwargs["query_text"] == USER_QUERY

    mock_build_prompt.assert_called_once()
    rag_context_arg = mock_build_prompt.call_args.args[0]
    retrieved_memories = rag_context_arg.relevant_memories
    assert len(retrieved_memories) == 1
    assert retrieved_memories[0].value == MAIN_ROOM_MEMORY_VALUE
