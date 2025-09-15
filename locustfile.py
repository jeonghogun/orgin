from locust import HttpUser, task, between
import random
import uuid

# This is a mock token that would be acquired through a real login flow.
# For testing purposes, we assume auth is optional or use a valid dev token.
# In a real scenario, the on_start method would handle authentication.
DEV_JWT_TOKEN = "your-development-jwt-token-here"

class OriginUser(HttpUser):
    wait_time = between(1, 5)  # Simulate users waiting 1-5 seconds between tasks
    host = "http://localhost:8080" # Assuming Nginx is running on 8080

    def on_start(self):
        """Called when a Locust user starts"""
        self.headers = {"Authorization": f"Bearer {DEV_JWT_TOKEN}"}
        self.user_id = f"locust_user_{uuid.uuid4()}"
        self.main_room_id = None
        self.sub_room_id = None

        # Each user should create their own main room to work in
        self.create_main_room()

    def create_main_room(self):
        try:
            with self.client.post(
                "/api/rooms",
                headers=self.headers,
                json={"name": f"Main Room {self.user_id}", "type": "main"},
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    self.main_room_id = response.json()["room_id"]
                elif response.status_code == 400 and "already exists" in response.text:
                    # If main room exists, try to find it
                    with self.client.get("/api/rooms", headers=self.headers) as get_response:
                        rooms = get_response.json()
                        main_room = next((r for r in rooms if r["type"] == "main"), None)
                        if main_room:
                            self.main_room_id = main_room["room_id"]
                else:
                    response.failure(f"Could not create or find main room. Status: {response.status_code}")
        except Exception as e:
            pass # Fail silently if setup fails

    @task(5)
    def send_chat_message(self):
        """Simulates a user sending a message to their main room."""
        if not self.main_room_id:
            return

        self.client.post(
            f"/api/rooms/{self.main_room_id}/messages/stream",
            headers=self.headers,
            name="/api/rooms/[roomId]/messages/stream",
            json={"content": f"This is a test message from {self.user_id} at {random.randint(1, 1000)}"}
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
            catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure("Failed to create sub-room")
                return
            sub_room_id = response.json()["room_id"]

        # 2. Start a review in the new sub-room
        review_topic = f"Analysis of topic {random.randint(1, 1000)}"
        self.client.post(
            f"/api/rooms/{sub_room_id}/create-review-room",
            headers=self.headers,
            name="/api/rooms/[parentId]/create-review-room",
            json={"topic": review_topic, "history": []}
        )

    @task(2)
    def list_rooms(self):
        """Simulates a user fetching their list of rooms."""
        self.client.get("/api/rooms", headers=self.headers)
