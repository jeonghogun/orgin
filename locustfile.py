import os
import random
import uuid

from locust import HttpUser, between, task


DEV_JWT_TOKEN = os.getenv("LOCUST_JWT_TOKEN", "dev-jwt-token-placeholder")
DEFAULT_HOST = os.getenv("LOCUST_HOST", "http://localhost:8080")


class OriginUser(HttpUser):
    wait_time = between(1, 5)  # Simulate users waiting 1-5 seconds between tasks
    host = DEFAULT_HOST

    def on_start(self):
        """Called when a Locust user starts"""
        self.headers = {"Authorization": f"Bearer {DEV_JWT_TOKEN}"}
        self.user_id = f"locust_user_{uuid.uuid4()}"
        self.main_room_id = None

        # Each user should create their own main room to work in
        self.create_main_room()

    def create_main_room(self):
        payload = {"name": f"Main Room {self.user_id}", "type": "main"}
        try:
            with self.client.post(
                "/api/rooms",
                headers=self.headers,
                json=payload,
                catch_response=True,
                name="/api/rooms (create main)",
            ) as response:
                if response.status_code in (200, 201):
                    self.main_room_id = response.json()["room_id"]
                    return

                if response.status_code == 400 and "already exists" in response.text.lower():
                    with self.client.get(
                        "/api/rooms",
                        headers=self.headers,
                        name="/api/rooms (list)",
                    ) as get_response:
                        if get_response.status_code == 200:
                            rooms = get_response.json()
                            main_room = next(
                                (r for r in rooms if r.get("type") == "main"),
                                None,
                            )
                            if main_room:
                                self.main_room_id = main_room["room_id"]
                                return
                response.failure(
                    f"Could not create or find main room. Status: {response.status_code}"
                )
        except Exception:
            # Allow the test user to continue even if setup failed.
            return

    @task(5)
    def send_chat_message(self):
        """Simulates a user sending a message to their main room."""
        if not self.main_room_id:
            return

        message_payload = {
            "content": (
                "This is a test message from "
                f"{self.user_id} at {random.randint(1, 1000)}"
            )
        }
        self.client.post(
            f"/api/rooms/{self.main_room_id}/messages/stream",
            headers=self.headers,
            name="/api/rooms/[roomId]/messages/stream",
            json=message_payload,
        )

    @task(1)
    def create_sub_room_and_start_review(self):
        """Simulates creating a sub-room and then starting a review in it."""
        if not self.main_room_id:
            return

        # 1. Create a sub-room
        sub_room_name = f"Sub-Room {random.randint(1, 100)}"
        with self.client.post(
            "/api/rooms",
            headers=self.headers,
            name="/api/rooms (create sub)",
            json={"name": sub_room_name, "type": "sub", "parent_id": self.main_room_id},
            catch_response=True,
        ) as response:
            if response.status_code not in (200, 201):
                response.failure("Failed to create sub-room")
                return
            sub_room_id = response.json()["room_id"]

        # 2. Start a review in the new sub-room
        review_topic = f"Analysis of topic {random.randint(1, 1000)}"
        review_payload = {
            "topic": review_topic,
            "instruction": "테스트 시나리오용 자동 생성 리뷰",
        }
        self.client.post(
            f"/api/rooms/{sub_room_id}/reviews",
            headers=self.headers,
            name="/api/rooms/[roomId]/reviews",
            json=review_payload,
        )

    @task(2)
    def list_rooms(self):
        """Simulates a user fetching their list of rooms."""
        self.client.get("/api/rooms", headers=self.headers, name="/api/rooms (list)")
