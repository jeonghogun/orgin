import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch

# Import the mock LLM function from conftest to simulate AI responses
from tests.conftest import mock_llm_invoke

@pytest.mark.anyio
def test_e2e_multi_agent_review(clean_authenticated_client: TestClient):
    """
    Tests the full end-to-end flow of creating a review,
    running the multi-agent debate, and verifying the final report in the database.
    This test relies on the `celery_eager` fixture from conftest.
    """
    # 1. ARRANGE: Set up rooms and mock the LLM service
    # We patch the synchronous LLM invoke method, as this is what the Celery workers will call.
    with patch("app.services.llm_service.LLMService.invoke_sync", new=mock_llm_invoke):

        # Create a main room for the user
        main_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "E2E Main Room", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        # Create a sub room where the review will be initiated
        sub_room_res = clean_authenticated_client.post(
            "/api/rooms",
            json={"name": "E2E Sub Room", "type": "sub", "parent_id": main_room_id}
        )
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        # 2. ACT: Create a new review and trigger the generation process

        # 2.1. Create the review object
        create_review_res = clean_authenticated_client.post(
            f"/api/rooms/{sub_room_id}/reviews",
            json={"topic": "Future of AI", "instruction": "Discuss the future of AI."}
        )
        assert create_review_res.status_code == 200
        review_id = create_review_res.json()["review_id"]
        assert review_id is not None

        # 3. ASSERT: Verify the review was created and completed
        # Wait for the review to complete (with timeout)
        import time
        timeout = 30  # seconds
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status_res = clean_authenticated_client.get(f"/api/reviews/{review_id}")
            assert status_res.status_code == 200
            status_data = status_res.json()
            
            if status_data["status"] == "completed":
                break
            elif status_data["status"] == "failed":
                pytest.fail(f"Review failed: {status_data}")
            
            time.sleep(1)
        
        # Verify final status
        final_status_res = clean_authenticated_client.get(f"/api/reviews/{review_id}")
        assert final_status_res.status_code == 200
        final_status_data = final_status_res.json()
        assert final_status_data["status"] == "completed"
        
        # Verify the final report exists
        report_res = clean_authenticated_client.get(f"/api/reviews/{review_id}/report")
        assert report_res.status_code == 200
        report_data = report_res.json()
        
        # Verify report structure
        assert "data" in report_data
        report = report_data["data"]
        assert "topic" in report
        assert "instruction" in report
        assert "executive_summary" in report
        assert "alternatives" in report
        assert "recommendations" in report
        
        # Verify report content matches what we sent
        assert report["topic"] == "Future of AI"
        assert report["instruction"] == "Discuss the future of AI."
