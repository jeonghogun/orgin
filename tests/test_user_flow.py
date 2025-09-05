import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
import app.tasks.persona_tasks

@pytest.mark.asyncio
async def test_full_user_journey(authenticated_client: TestClient, monkeypatch):
    """
    Tests a full user journey using the live test database.
    1. Create a main room.
    2. Create a sub-room within the main room.
    3. Send a message to the sub-room.
    4. Start a review in the sub-room.

    The global patch_llm_service fixture handles mocking LLM calls.
    """
    # We still need to mock the celery task for persona generation specifically for this test.
    monkeypatch.setattr(app.tasks.persona_tasks, "generate_user_persona", AsyncMock())

    # --- 1. Create Main Room ---
    main_room_name = "My Main E2E Room"
    main_room_res = authenticated_client.post(
        "/api/rooms",
        json={"name": main_room_name, "type": "main"}
    )
    assert main_room_res.status_code == 200, f"Failed to create main room: {main_room_res.text}"
    main_room_data = main_room_res.json()
    main_room_id = main_room_data["room_id"]
    assert main_room_data["name"] == main_room_name

    # --- 2. Create Sub Room ---
    sub_room_name = "My Sub-Room for Review"
    sub_room_res = authenticated_client.post(
        "/api/rooms",
        json={"name": sub_room_name, "type": "sub", "parent_id": main_room_id}
    )
    assert sub_room_res.status_code == 200, f"Failed to create sub-room: {sub_room_res.text}"
    sub_room_data = sub_room_res.json()
    sub_room_id = sub_room_data["room_id"]
    assert sub_room_data["name"] == sub_room_name
    assert sub_room_data["parent_id"] == main_room_id

    # --- 3. Send a Message ---
    message_content = "This is the message we will create a review for."
    msg_res = authenticated_client.post(
        f"/api/rooms/{sub_room_id}/messages",
        json={"content": message_content}
    )
    assert msg_res.status_code == 200, f"Failed to send message: {msg_res.text}"
    assert "ai_response" in msg_res.json()["data"]

    # --- 4. Create and Start a Review ---
    review_topic = "Analyzing the test message"
    review_instruction = "Please analyze the sentiment of the message."
    review_res = authenticated_client.post(
        f"/api/rooms/{sub_room_id}/reviews",
        json={"topic": review_topic, "instruction": review_instruction}
    )
    assert review_res.status_code == 200, f"Failed to create review: {review_res.text}"
    review_data = review_res.json()
    assert review_data["topic"] == review_topic
    assert review_data["status"] == "pending"
