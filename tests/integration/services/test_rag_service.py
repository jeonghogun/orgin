import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.rag_service import RAGService
from tests.conftest import USER_ID

@pytest.mark.anyio
async def test_rag_hybrid_end_to_end(authenticated_client: TestClient, db_session):
    """
    Tests that the RAG service uses the hybrid retrieval method and
    correctly passes the context to the LLM.
    """
    # 1. Setup: Create rooms and seed messages
    # Main room
    main_res = authenticated_client.post("/api/rooms", json={"name": "Main", "type": "main"})
    main_room_id = main_res.json()["room_id"]
    authenticated_client.post(f"/api/rooms/{main_room_id}/messages", json={"content": "This is a memory about python programming."})

    # Sub room
    sub_res = authenticated_client.post("/api/rooms", json={"name": "Sub", "type": "sub", "parent_id": main_room_id})
    sub_room_id = sub_res.json()["room_id"]
    authenticated_client.post(f"/api/rooms/{sub_room_id}/messages", json={"content": "A specific message about fastapi."})

    # 2. Mock the final LLM call to capture the prompt
    mock_llm_service = AsyncMock(spec=LLMService)
    mock_llm_service.generate_embedding.return_value = ([0.1] * 1536, {}) # Mock embedding

    # We want to inspect the prompt passed to the final call
    final_prompt_spy = AsyncMock(return_value=("Final response", {}))
    mock_llm_service.get_provider.return_value.invoke = final_prompt_spy

    # Override the dependency
    from app.api.dependencies import get_rag_service
    rag_service = get_rag_service()
    rag_service.llm_service = mock_llm_service
    app.dependency_overrides[get_rag_service] = lambda: rag_service

    # 3. Trigger the RAG service by sending a message
    query = "Tell me about python and fastapi."
    authenticated_client.post(f"/api/rooms/{sub_room_id}/messages", json={"content": query})

    # 4. Assert that the prompt contains the retrieved memories
    final_prompt_spy.assert_called_once()
    rag_prompt = final_prompt_spy.call_args[1]['user_prompt']

    assert "--- Relevant Past Conversations ---" in rag_prompt
    assert "python programming" in rag_prompt # From main room
    assert "fastapi" in rag_prompt # From sub room

    # Cleanup
    app.dependency_overrides = {}
