import pytest
from unittest.mock import patch, AsyncMock

@patch("app.services.fact_extractor_service.FactExtractorService.extract_facts_from_message")
@patch("app.services.user_fact_service.UserFactService.save_fact")
def test_fact_pipeline_e2e(
    mock_save_fact: AsyncMock,
    mock_extract_facts: AsyncMock,
    authenticated_client
):
    """
    Tests that sending a message triggers the fact extraction and saving pipeline.
    """
    test_room_id = "test_pipeline_room"
    user_message = "My name is Integration Test and my hobby is testing."

    extracted_facts = [
        {"type": "user_name", "value": "Integration Test", "confidence": 0.9},
        {"type": "hobby", "value": "testing", "confidence": 0.85},
    ]
    mock_extract_facts.return_value = extracted_facts

    response = authenticated_client.post(
        f"/{test_room_id}/messages",
        json={"content": user_message}
    )

    assert response.status_code == 200
    mock_extract_facts.assert_called_once()
    assert mock_save_fact.call_count == len(extracted_facts)
