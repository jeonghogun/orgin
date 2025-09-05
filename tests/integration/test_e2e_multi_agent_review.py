import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch

# Import the mock LLM function from conftest to simulate AI responses
from tests.conftest import mock_llm_invoke, USER_ID

@pytest.mark.anyio
def test_e2e_multi_agent_review(authenticated_client: TestClient, db_session):
    """
    Tests the full end-to-end flow of creating a review,
    running the multi-agent debate, and verifying the final report in the database.
    This test relies on the `celery_eager` fixture from conftest.
    """
    # 1. ARRANGE: Set up rooms and mock the LLM service
    # We patch the synchronous LLM invoke method, as this is what the Celery workers will call.
    with patch("app.services.llm_service.LLMService.invoke_sync", new=mock_llm_invoke):

        # Create a main room for the user
        main_room_res = authenticated_client.post("/api/rooms", json={"name": "E2E Main Room", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        # Create a sub room where the review will be initiated
        sub_room_res = authenticated_client.post(
            "/api/rooms",
            json={"name": "E2E Sub Room", "type": "sub", "parent_id": main_room_id}
        )
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        # 2. ACT: Create a new review and trigger the generation process

        # 2.1. Create the review object
        create_review_res = authenticated_client.post(
            f"/api/rooms/{sub_room_id}/reviews",
            json={"topic": "Future of AI", "instruction": "Discuss the future of AI."}
        )
        assert create_review_res.status_code == 200
        review_id = create_review_res.json()["data"]["review_id"]
        assert review_id is not None

        # 2.2. Trigger the review generation
        # Because of the `celery_eager` setting, this API call will block until all tasks are done.
        generate_res = authenticated_client.post(f"/api/reviews/{review_id}/generate")
        assert generate_res.status_code == 200
        assert generate_res.json()["message"] == "Review process started successfully."

        # 3. ASSERT: Verify the final state directly in the database
        cursor = db_session.cursor()

        # 3.1. Check the main review status
        cursor.execute("SELECT status, current_round, final_report FROM reviews WHERE review_id = %s", (review_id,))
        review_row = cursor.fetchone()
        assert review_row is not None, "Review row not found in database"
        review_status, current_round, final_report_json = review_row

        assert review_status == "completed"
        assert current_round == 3
        assert final_report_json is not None

        # 3.2. Check the content of the final report
        final_report = json.loads(final_report_json)
        assert final_report["topic"] == "E2E Test Topic"  # This comes from the mock_llm_invoke
        assert final_report["recommendation"] == "adopt"

        # 3.3. Check for panel reports (at least for the final round)
        cursor.execute("SELECT COUNT(*) FROM panel_reports WHERE review_id = %s AND round_num = %s", (review_id, 3))
        panel_report_count = cursor.fetchone()[0]
        assert panel_report_count >= 1  # Should ideally be 3 if all panelists succeed

        # 3.4. Check for consolidated reports
        cursor.execute("SELECT COUNT(*) FROM consolidated_reports WHERE review_id = %s", (review_id,))
        consolidated_report_count = cursor.fetchone()[0]
        assert consolidated_report_count == 3  # For rounds 1, 2, and 3

    db_session.close()
