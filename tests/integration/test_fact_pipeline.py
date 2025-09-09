import pytest
from unittest.mock import patch, AsyncMock

@patch("app.services.fact_extractor_service.FactExtractorService.extract_facts_from_message")
@patch("app.services.user_fact_service.UserFactService.save_fact")
def test_fact_pipeline_e2e(
    mock_save_fact: AsyncMock,
    mock_extract_facts: AsyncMock,
    clean_authenticated_client
):
    """
    Tests that sending a message triggers the fact extraction and saving pipeline.
    """
    # Create a room first
    room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Test Pipeline Room", "type": "main"})
    assert room_res.status_code == 200
    test_room_id = room_res.json()["room_id"]
    
    user_message = "My name is Integration Test and my hobby is testing."

    extracted_facts = [
        {"type": "user_name", "value": "Integration Test", "confidence": 0.9},
        {"type": "hobby", "value": "testing", "confidence": 0.85},
    ]
    mock_extract_facts.return_value = extracted_facts

    response = clean_authenticated_client.post(
        f"/api/rooms/{test_room_id}/messages",
        json={"content": user_message}
    )

    assert response.status_code == 200
    # The fact extraction is called twice due to the message processing pipeline
    assert mock_extract_facts.call_count == 2
    # Each fact is saved twice (once for each extraction call)
    assert mock_save_fact.call_count == len(extracted_facts) * 2
