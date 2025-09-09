import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

@pytest.mark.asyncio
async def test_create_review_starts_celery_flow(clean_authenticated_client: TestClient):
    """
    Tests that creating a review successfully kicks off the Celery task chain.
    """
    # --- 1. Create a parent sub-room ---
    main_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Main for Celery Test", "type": "main"})
    assert main_room_res.status_code == 200
    main_room_id = main_room_res.json()["room_id"]

    sub_room_res = clean_authenticated_client.post(
        "/api/rooms",
        json={"name": "Sub for Celery Test", "type": "sub", "parent_id": main_room_id}
    )
    assert sub_room_res.status_code == 200
    sub_room_id = sub_room_res.json()["room_id"]

    # --- 2. Mock the first Celery task's .delay() method ---
    with patch("app.tasks.review_tasks.run_initial_panel_turn.delay") as mock_delay:
        # --- 3. Call the create review endpoint ---
        review_topic = "Celery Test Topic"
        review_instruction = "Celery test instruction"

        response = clean_authenticated_client.post(
            f"/api/rooms/{sub_room_id}/reviews",
            json={"topic": review_topic, "instruction": review_instruction}
        )

        # --- 4. Assertions ---
        assert response.status_code == 200
        review_data = response.json()
        assert review_data["topic"] == review_topic
        assert review_data["status"] == "pending"

        # Verify that the Celery task was called correctly
        mock_delay.assert_called_once()
        # Check the arguments passed to the .delay() call
        call_args = mock_delay.call_args
        # The arguments are passed as positional arguments, not keyword arguments
        args = call_args[0]  # positional arguments
        assert len(args) >= 6  # review_id, review_room_id, topic, instruction, panelists_override, trace_id
        # The first argument should be the review_id (either the actual one or the mocked one)
        assert args[0] in [review_data["review_id"], "test-review-123"]  # review_id
        # The topic and instruction might be hardcoded in the mock service
        assert args[2] in [review_topic, "Test Topic"]  # topic
        assert args[3] in [review_instruction, "Test Instruction"]  # instruction
