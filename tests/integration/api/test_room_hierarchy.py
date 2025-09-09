from fastapi.testclient import TestClient
from unittest.mock import patch


class TestRoomHierarchy:
    """Tests for room creation and hierarchy rules using the live test database."""

    def test_create_main_room_success(self, clean_authenticated_client: TestClient, test_user_id: str):
        """Test creating a main room successfully."""
        response = clean_authenticated_client.post("/api/rooms", json={"name": "My Main Room", "type": "main"})
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "main"
        assert data["owner_id"] == test_user_id

    def test_create_main_room_fails_if_already_exists(self, clean_authenticated_client: TestClient):
        """A user cannot create more than one main room."""
        # First, create one main room, which should succeed.
        response1 = clean_authenticated_client.post("/api/rooms", json={"name": "First Main", "type": "main"})
        assert response1.status_code == 200

        # Now, try to create another, which should fail.
        response2 = clean_authenticated_client.post("/api/rooms", json={"name": "Second Main", "type": "main"})
        assert response2.status_code == 400
        assert "Main room already exists" in response2.json()["error"]["message"]

    def test_create_sub_room_success(self, clean_authenticated_client: TestClient):
        """Test creating a sub room successfully."""
        # Create a main room to be the parent
        main_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Main for Sub", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        # Create the sub-room
        response = clean_authenticated_client.post("/api/rooms", json={"name": "My Sub Room", "type": "sub", "parent_id": main_room_id})
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "sub"
        assert data["parent_id"] == main_room_id

    def test_create_sub_room_fails_with_invalid_parent_type(self, clean_authenticated_client: TestClient):
        """Test creating a sub room fails if the parent is not a main room."""
        # Create a main room, and a sub-room within it.
        main_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Main Room", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        sub_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Sub Room 1", "type": "sub", "parent_id": main_room_id})
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        # Try to create a sub-room with another sub-room as its parent.
        response = clean_authenticated_client.post("/api/rooms", json={"name": "Sub Room 2", "type": "sub", "parent_id": sub_room_id})
        assert response.status_code == 400
        assert "must have a main room as a parent" in response.json()["error"]["message"]

    def test_delete_room_logic(self, clean_authenticated_client: TestClient):
        """Test deleting a sub-room."""
        # Create a main room and a sub-room
        main_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Main for Delete", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        sub_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Sub to Delete", "type": "sub", "parent_id": main_room_id})
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        # Delete the sub-room
        delete_res = clean_authenticated_client.delete(f"/api/rooms/{sub_room_id}")
        assert delete_res.status_code == 204

        # Verify it's gone
        get_res = clean_authenticated_client.get(f"/api/rooms/{sub_room_id}")
        assert get_res.status_code == 404

    def test_create_review_fails_from_main_room(self, clean_authenticated_client: TestClient):
        """A review can only be created from a sub-room, not a main room."""
        # Create a main room
        main_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Main for Review Fail", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        # Attempt to create a review from the main room
        response = clean_authenticated_client.post(
            f"/api/rooms/{main_room_id}/reviews",
            json={"topic": "Test Topic", "instruction": "Test Instruction"}
        )
        assert response.status_code == 400
        assert "Reviews can only be created from sub-rooms" in response.json()["detail"]

    def test_create_review_success_from_sub_room(self, clean_authenticated_client: TestClient):
        """Test creating a review from a sub-room successfully."""
        # 1. Create parent rooms
        main_room_res = clean_authenticated_client.post("/api/rooms", json={"name": "Main for Review", "type": "main"})
        assert main_room_res.status_code == 200
        main_room_id = main_room_res.json()["room_id"]

        sub_room_res = clean_authenticated_client.post(
            "/api/rooms",
            json={"name": "Sub for Review", "type": "sub", "parent_id": main_room_id}
        )
        assert sub_room_res.status_code == 200
        sub_room_id = sub_room_res.json()["room_id"]

        # 2. Mock the celery task's .delay method to prevent it from actually running
        with patch("app.tasks.review_tasks.run_initial_panel_turn.delay") as mock_delay:
            # 3. Create the review
            response = clean_authenticated_client.post(
                f"/api/rooms/{sub_room_id}/reviews",
                json={"topic": "Review Topic", "instruction": "Review Instruction"}
            )

            # 4. Assert success
            assert response.status_code == 200
            data = response.json()
            # Review room should have a different ID than the sub room
            assert data["room_id"] != sub_room_id
            # Check that the review was created with correct data
            assert data["topic"] == "Review Topic"
            assert data["instruction"] == "Review Instruction"
            assert data["status"] == "pending"
            mock_delay.assert_called_once()
