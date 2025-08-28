import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from tests.conftest import mock_llm_invoke
from app.tasks.review_tasks import (
    initial_turn_logic,
    rebuttal_turn_logic,
    synthesis_turn_logic,
    report_and_metrics_logic,
)

@pytest.mark.e2e
@patch("app.services.llm_service.ClaudeProvider.invoke", new_callable=AsyncMock)
@patch("app.services.llm_service.GeminiProvider.invoke", new_callable=AsyncMock)
@patch("app.services.llm_service.OpenAIProvider.invoke", new_callable=AsyncMock)
@patch("app.services.review_service.ReviewService.start_review_process", new_callable=AsyncMock)
async def test_full_review_flow_e2e(mock_start_review, mock_openai_invoke, mock_gemini_invoke, mock_claude_invoke, authenticated_client: TestClient):
    """
    Tests the full, end-to-end review flow, ensuring all three LLM providers are called.
    """
    # 1. Configure mocks for each provider to return a unique, identifiable response.
    mock_openai_invoke.return_value = ('{"summary": "OpenAI response"}', {})
    mock_gemini_invoke.return_value = ('{"summary": "Gemini response"}', {})
    mock_claude_invoke.return_value = ('{"summary": "Claude response"}', {})

    # 2. Define a side effect for the mocked service method that simulates the whole chain
    async def mock_review_process(review_id: str, topic: str, instruction: str):
        request_id = "test-e2e-request"

        # Round 1
        turn_1_outputs, round_1_metrics = await initial_turn_logic(
            review_id, topic, instruction, f"{request_id}-r1"
        )

        # Assert that the correct providers were called for the initial turn
        mock_openai_invoke.assert_called_once()
        mock_gemini_invoke.assert_called_once()
        mock_claude_invoke.assert_not_called() # We didn't request Claude

        # Assert that the output contains the correct responses
        responses = [output.get("summary") for output in turn_1_outputs.values()]
        assert "OpenAI response" in responses
        assert "Gemini response" in responses
        assert "Claude response" not in responses

        # For the rest of the flow, we need a generic mock for summarization etc.
        # Let's point the OpenAI mock (default) to the conftest helper for this.
        mock_openai_invoke.side_effect = mock_llm_invoke
        mock_gemini_invoke.side_effect = mock_llm_invoke # Not used, but safe
        mock_claude_invoke.side_effect = mock_llm_invoke # Not used, but safe

        # Round 2
        turn_2_outputs, round_2_metrics = await rebuttal_turn_logic(
            review_id, turn_1_outputs, f"{request_id}-r2"
        )

        # Round 3
        all_metrics = [round_1_metrics, round_2_metrics]
        turn_3_outputs, round_3_metrics = await synthesis_turn_logic(
            review_id, turn_1_outputs, turn_2_outputs, f"{request_id}-r3"
        )
        all_metrics.append(round_3_metrics)

        # Final Report
        await report_and_metrics_logic(
            review_id, turn_3_outputs, all_metrics, f"{request_id}-final"
        )

    mock_start_review.side_effect = mock_review_process

    # --- Setup: Create parent rooms ---
    main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for E2E", "type": "main"})
    assert main_room_res.status_code == 200
    main_room_id = main_room_res.json()["room_id"]

    sub_room_res = authenticated_client.post(
        "/api/rooms",
        json={"name": "Sub for E2E", "type": "sub", "parent_id": main_room_id}
    )
    assert sub_room_res.status_code == 200
    sub_room_id = sub_room_res.json()["room_id"]

    # --- Trigger the review with a custom panel ---
    review_topic = "E2E Test Topic"
    review_instruction = "E2E test instruction"
    custom_panelists = ["openai", "gemini"] # Test with a subset of providers

    create_review_res = authenticated_client.post(
        f"/api/rooms/{sub_room_id}/reviews",
        json={"topic": review_topic, "instruction": review_instruction, "panelists": custom_panelists}
    )
    assert create_review_res.status_code == 200
    review_id = create_review_res.json()["review_id"]
    assert review_id is not None

    # --- Poll for completion ---
    timeout_seconds = 60
    start_time = time.time()
    review_status = ""
    while time.time() - start_time < timeout_seconds:
        status_res = authenticated_client.get(f"/api/reviews/{review_id}")
        assert status_res.status_code == 200
        review_status = status_res.json()["status"]
        if review_status == "completed":
            break
        elif review_status == "failed":
            pytest.fail(f"Review process failed. Final status: {status_res.json()}")
        time.sleep(2)

    assert review_status == "completed", f"Review did not complete within {timeout_seconds} seconds."

    # --- Fetch and validate the final report ---
    report_res = authenticated_client.get(f"/api/reviews/{review_id}/report")
    assert report_res.status_code == 200

    report_data = report_res.json()["data"]
    assert report_data is not None
    assert report_data["topic"] == review_topic
    assert "recommendation" in report_data

    print(f"E2E review flow for {review_id} completed and report validated successfully.")


@pytest.mark.e2e
@patch("app.tasks.review_tasks.LLMService")
async def test_review_flow_with_provider_fallback(mock_llm_class, authenticated_client: TestClient):
    """
    Tests that the full E2E review flow completes successfully even if one provider
    fails, demonstrating the fallback logic.
    """
    # 1. Configure mocks
    mock_llm_instance = mock_llm_class.return_value

    # Gemini will fail, forcing a fallback. OpenAI and Claude will succeed.
    # We use the conftest helper to generate realistic-looking JSON responses.
    async def invoke_side_effect(*args, **kwargs):
        if kwargs.get('request_id', '').endswith('-gemini'):
            raise Exception("Gemini provider failed!")
        # The fallback and other providers will use the mock helper
        return mock_llm_invoke(*args, **kwargs)

    mock_llm_instance.get_provider.return_value.invoke.side_effect = invoke_side_effect

    # 2. Setup rooms
    main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for Fallback", "type": "main"})
    main_room_id = main_room_res.json()["room_id"]
    sub_room_res = authenticated_client.post("/api/rooms", json={"name": "Sub for Fallback", "type": "sub", "parent_id": main_room_id})
    sub_room_id = sub_room_res.json()["room_id"]

    # 3. Trigger the review with all three panelists
    create_review_res = authenticated_client.post(
        f"/api/rooms/{sub_room_id}/reviews",
        json={"topic": "Fallback Test", "instruction": "Test", "panelists": ["openai", "gemini", "claude"]}
    )
    assert create_review_res.status_code == 200
    review_id = create_review_res.json()["review_id"]

    # 4. Poll for completion (same as the happy path test)
    timeout_seconds = 60
    start_time = time.time()
    review_status = ""
    while time.time() - start_time < timeout_seconds:
        status_res = authenticated_client.get(f"/api/reviews/{review_id}")
        assert status_res.status_code == 200
        review_status = status_res.json()["status"]
        if review_status == "completed":
            break
        time.sleep(2)

    assert review_status == "completed", "Review did not complete after a provider failure."
