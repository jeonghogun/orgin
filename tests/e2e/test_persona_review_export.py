"""
End-to-end test for the core user journey:
Persona Generation -> Review -> Export
"""
import pytest
import json
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_service import LLMService, LLMProvider
from tests.conftest import USER_ID, mock_llm_invoke
from app.tasks.persona_tasks import generate_user_persona


@pytest.mark.anyio
async def test_persona_review_export_e2e(authenticated_client: TestClient, db_session):
    """
    Tests the full user journey from seeding data to exporting the final report.
    """
    # 1. Mock the LLM Service to avoid real API calls
    mock_provider = AsyncMock(spec=LLMProvider)
    mock_provider.invoke.side_effect = mock_llm_invoke

    mock_llm_service = LLMService()
    mock_llm_service.get_provider = lambda provider_name="openai": mock_provider

    app.dependency_overrides[LLMService] = lambda: mock_llm_service

    # === A) Create Main/Sub rooms; seed messages in Main ===
    # Create Main room
    response = authenticated_client.post("/api/rooms", json={"name": "Main Room", "type": "main"})
    assert response.status_code == 200
    main_room = response.json()
    assert main_room["type"] == "main"

    # Seed messages in Main room
    for i in range(5):
        authenticated_client.post(
            f"/api/rooms/{main_room['room_id']}/messages",
            json={"content": f"This is message {i} about AI and technology."}
        )

    # Create Sub room
    response = authenticated_client.post(
        "/api/rooms",
        json={"name": "E2E Test Sub Room", "type": "sub", "parent_id": main_room["room_id"]}
    )
    assert response.status_code == 200
    sub_room = response.json()
    assert sub_room["parent_id"] == main_room["room_id"]

    # === B) Trigger persona generation; wait until profile populated ===
    # In a real app, this might be a scheduled task. For the test, we trigger it directly.
    # Since celery is in eager mode, this runs synchronously.
    generate_user_persona.delay(user_id=USER_ID)

    # Verify profile was updated (optional, but good practice)
    # We'd need a profile GET endpoint for this, which doesn't exist.
    # We'll assume it worked and verify its effect via the review.

    # === C) Start multi-provider review; wait for completion ===
    review_payload = {
        "topic": "E2E Test Topic",
        "instruction": "Analyze the impact.",
        "panelists": ["openai", "gemini", "claude"]
    }
    response = authenticated_client.post(f"/api/rooms/{sub_room['room_id']}/reviews", json=review_payload)
    assert response.status_code == 200
    review = response.json()
    review_id = review["review_id"]

    # The Celery tasks run eagerly, so the review should be complete.
    # We can verify by checking the review status.
    response = authenticated_client.get(f"/api/reviews/{review_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    # === D) Call export endpoint and verify contents ===
    # Test JSON export
    response_json = authenticated_client.get(f"/api/rooms/{sub_room['room_id']}/export?format=json")
    assert response_json.status_code == 200
    export_data = response_json.json()

    assert export_data["room_id"] == sub_room["room_id"]
    assert len(export_data["messages"]) == 0 # Messages were in main room, not sub
    assert len(export_data["reviews"]) == 1

    exported_review = export_data["reviews"][0]
    assert exported_review["topic"] == "E2E Test Topic"
    assert "This is the executive summary." in exported_review["final_summary"]
    assert "Alternative 1" in exported_review["next_steps"]
    assert "Final Recommendation: adopt" in exported_review["next_steps"]

    # Test Markdown export
    response_md = authenticated_client.get(f"/api/rooms/{sub_room['room_id']}/export?format=markdown")
    assert response_md.status_code == 200
    assert response_md.headers["content-type"] == "text/markdown"
    assert f"export_room_{sub_room['room_id']}.md" in response_md.headers["content-disposition"]

    markdown_content = response_md.text
    assert "# Export for Room: E2E Test Sub Room" in markdown_content
    assert "## Chat History" in markdown_content
    assert "### Review 1: E2E Test Topic" in markdown_content
    assert "This is the executive summary." in markdown_content
    assert "- Alternative 1" in markdown_content
    assert "- Final Recommendation: adopt" in markdown_content

    # Cleanup dependency override
    app.dependency_overrides = {}
