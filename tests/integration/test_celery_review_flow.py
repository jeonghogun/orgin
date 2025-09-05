import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

@pytest.mark.asyncio
async def test_create_review_starts_celery_flow(authenticated_client: TestClient):
    """
    Tests that creating a review successfully kicks off the Celery task chain.
    """
    # --- 1. Create a parent sub-room ---
    main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for Celery Test", "type": "main"})
    assert main_room_res.status_code == 200
    main_room_id = main_room_res.json()["room_id"]

    sub_room_res = authenticated_client.post(
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

        response = authenticated_client.post(
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
        call_kwargs = mock_delay.call_args.kwargs
        assert call_kwargs["review_id"] == review_data["review_id"]
        assert call_kwargs["topic"] == review_topic
        assert call_kwargs["instruction"] == review_instruction
