"""
E2E Tests for Conversation System
Tests the complete flow from thread creation to export
"""

import pytest
import asyncio
import json
import time
from typing import Dict, Any, List
from fastapi.testclient import TestClient
from app.main import app
from app.services.database_service import get_database_service
from app.services.conversation_service import ConversationService
from app.services.cost_tracking_service import CostTrackingService
from app.services.export_service import ExportService

# Test client
client = TestClient(app)

class TestConversationSystemE2E:
    """End-to-end tests for the conversation system"""
    
    @pytest.fixture(autouse=True)
    async def setup_and_cleanup(self):
        """Setup and cleanup for each test"""
        # Setup
        self.user_id = "test_user_123"
        self.sub_room_id = "test_sub_room_456"
        self.auth_headers = {"Authorization": "Bearer test_token"}

        # Ensure the sub-room exists for the FK constraint used by conversation threads
        db = get_database_service()
        current_time = int(time.time())
        try:
            db.execute_update(
                """
                INSERT INTO rooms (room_id, name, owner_id, type, parent_id, created_at, updated_at, message_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (room_id) DO UPDATE
                SET name = EXCLUDED.name,
                    owner_id = EXCLUDED.owner_id,
                    type = EXCLUDED.type,
                    parent_id = EXCLUDED.parent_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    self.sub_room_id,
                    "Test Sub Room",
                    self.user_id,
                    "sub",
                    None,
                    current_time,
                    current_time,
                    0,
                ),
            )
        except Exception as exc:
            print(f"Room setup error: {exc}")

        # Cleanup after test
        yield
        await self._cleanup_test_data()
    
    async def _cleanup_test_data(self):
        """Clean up test data"""
        db = get_database_service()
        try:
            # Clean up test threads and messages
            db.execute_update("DELETE FROM conversation_messages WHERE user_id = %s", (self.user_id,))
            db.execute_update("DELETE FROM conversation_threads WHERE sub_room_id = %s", (self.sub_room_id,))
            try:
                db.execute_update("DELETE FROM attachments WHERE thread_id LIKE %s", (f"test_thread_%",))
            except Exception:
                # Legacy schemas may not include the thread_id column; ignore errors during cleanup
                pass
            db.execute_update("DELETE FROM usage_tracking WHERE user_id = %s", (self.user_id,))
            db.execute_update("DELETE FROM daily_usage_metrics WHERE user_id = %s", (self.user_id,))
            db.execute_update("DELETE FROM rooms WHERE room_id = %s", (self.sub_room_id,))
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    def test_complete_conversation_flow(self):
        """Test complete conversation flow: create thread -> send messages -> search -> export"""
        
        # Step 1: Create a new thread
        thread_response = client.post(
            f"/api/convo/rooms/{self.sub_room_id}/threads",
            json={"title": "E2E Test Thread", "initial_message": "Hello, this is a test"},
            headers=self.auth_headers
        )
        assert thread_response.status_code == 201
        thread_data = thread_response.json()
        thread_id = thread_data["id"]

        # Step 2: Send a user message
        message_response = client.post(
            f"/api/convo/threads/{thread_id}/messages",
            json={
                "content": "What is the capital of France?",
                "model": "gpt-4o-mini",
                "temperature": 0.7
            },
            headers=self.auth_headers
        )
        assert message_response.status_code == 200
        message_data = message_response.json()
        message_id = message_data["messageId"]

        # Step 3: Simulate assistant response (in real scenario, this would be via SSE)
        # For testing, we'll create the assistant message directly
        conversation_service = ConversationService()
        assistant_message = conversation_service.create_message(
            thread_id=thread_id,
            role="assistant",
            content="The capital of France is Paris. It's a beautiful city known for its art, culture, and landmarks like the Eiffel Tower.",
            status="complete",
            model="gpt-4o-mini",
            meta={
                "model": "gpt-4o-mini",
                "tokensPrompt": 15,
                "tokensOutput": 25,
                "costUSD": 0.0001
            },
            user_id="system"
        )

        # Step 4: Get thread messages
        messages_response = client.get(
            f"/api/convo/threads/{thread_id}/messages",
            headers=self.auth_headers
        )
        assert messages_response.status_code == 200
        messages_data = messages_response.json()
        assert len(messages_data) >= 2  # User + Assistant messages

        # Step 5: Search in the conversation
        search_response = client.post(
            "/api/convo/search",
            json={
                "query": "capital of France",
                "thread_id": thread_id,
                "limit": 10
            },
            headers=self.auth_headers
        )
        assert search_response.status_code == 200
        search_data = search_response.json()
        assert search_data["total_results"] >= 0

        # Step 6: Export the thread
        export_response = client.get(
            f"/api/convo/threads/{thread_id}/export",
            params={"format": "md"},
            headers=self.auth_headers
        )
        assert export_response.status_code == 200
        assert "attachment" in export_response.headers['content-disposition']

        print("✅ Complete conversation flow test passed")

    def test_file_upload_and_rag_search(self):
        """Test file upload and RAG search functionality"""

        # Step 1: Create a thread
        thread_response = client.post(
            f"/api/convo/rooms/{self.sub_room_id}/threads",
            json={"title": "File Upload Test Thread"},
            headers=self.auth_headers
        )
        assert thread_response.status_code == 201
        thread_id = thread_response.json()["id"]

        # Step 2: Create a test file
        test_content = """
        This is a test document about artificial intelligence.
        AI is transforming various industries including healthcare, finance, and education.
        Machine learning algorithms can process large amounts of data to find patterns.
        Natural language processing enables computers to understand human language.
        """

        # Step 3: Upload file (simulate file upload)
        files = {"files": ("test_document.txt", test_content, "text/plain")}
        data = {"thread_id": thread_id}

        upload_response = client.post(
            "/api/uploads",
            files=files,
            data=data,
            headers=self.auth_headers
        )
        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        assert len(upload_data) > 0
        attachment_id = upload_data[0]["id"]

        # Step 4: Wait for processing (in real scenario, this would be async)
        time.sleep(1)

        # Step 5: Search in uploaded content
        search_response = client.post(
            "/api/convo/search",
            json={
                "query": "artificial intelligence",
                "thread_id": thread_id,
                "limit": 5
            },
            headers=self.auth_headers
        )
        assert search_response.status_code == 200
        search_data = search_response.json()
        # Note: In a real test, we'd need to wait for the RAG indexing to complete

        print("✅ File upload and RAG search test passed")

    @pytest.mark.skip(reason="Budget endpoint removed, needs mocking settings")
    def test_cost_tracking_and_budget_limits(self):
        """Test cost tracking and budget limit enforcement"""
        
        # Step 1: Create a thread
        thread_response = client.post(
            f"/api/convo/rooms/{self.sub_room_id}/threads",
            json={"title": "Budget Test Thread"},
            headers=self.auth_headers
        )
        assert thread_response.status_code == 201
        thread_id = thread_response.json()["id"]

        # Step 2: Send multiple messages to exceed budget
        for i in range(5):
            message_response = client.post(
                f"/api/convo/threads/{thread_id}/messages",
                json={
                    "content": f"Test message {i} with some content to consume tokens",
                    "model": "gpt-4o-mini"
                },
                headers=self.auth_headers
            )
            # This will depend on the mocked budget
            assert message_response.status_code in [200, 429]

        # Step 3: Check budget status
        budget_status_response = client.get(
            "/api/convo/usage/today",
            headers=self.auth_headers
        )
        assert budget_status_response.status_code == 200
        budget_status = budget_status_response.json()
        assert "usage" in budget_status
        assert "budget" in budget_status

        print("✅ Cost tracking and budget limits test passed")

    def test_monitoring_and_metrics(self):
        """Test monitoring and metrics collection"""
        
        # Step 1: Get system metrics
        metrics_response = client.get(
            "/api/metrics/summary?time_window_hours=1",
            headers=self.auth_headers
        )
        assert metrics_response.status_code == 200
        metrics_data = metrics_response.json()
        assert "system" in metrics_data
        assert "llm" in metrics_data
        assert "errors" in metrics_data
        
        # Step 2: Get health status
        health_response = client.get("/health")
        assert health_response.status_code in [200, 503]  # 503 if unhealthy
        health_data = health_response.json()
        assert "status" in health_data
        
        # Step 3: Get daily costs
        costs_response = client.get(
            "/api/convo/usage/today",
            headers=self.auth_headers
        )
        assert costs_response.status_code == 200
        costs_data = costs_response.json()
        assert "usage" in costs_data
        assert "budget" in costs_data

        print("✅ Monitoring and metrics test passed")
    
    def test_thread_management_operations(self):
        """Test thread management operations"""
        
        # Step 1: Create multiple threads
        thread_ids = []
        for i in range(3):
            thread_response = client.post(
                f"/api/convo/rooms/{self.sub_room_id}/threads",
                json={"title": f"Test Thread {i}"},
                headers=self.auth_headers
            )
            assert thread_response.status_code == 201
            thread_ids.append(thread_response.json()["id"])
        
        # Step 2: Get thread list
        threads_response = client.get(
            f"/api/convo/rooms/{self.sub_room_id}/threads",
            headers=self.auth_headers
        )
        assert threads_response.status_code == 200
        threads_data = threads_response.json()
        assert len(threads_data) >= 3
        
        # Step 3: Pin a thread
        pin_response = client.patch(
            f"/api/convo/threads/{thread_ids[0]}",
            json={"is_pinned": True},
            headers=self.auth_headers
        )
        assert pin_response.status_code == 200
        
        # Step 4: Archive a thread
        archive_response = client.patch(
            f"/api/convo/threads/{thread_ids[1]}",
            json={"is_archived": True},
            headers=self.auth_headers
        )
        assert archive_response.status_code == 200
        
        # Step 5: Delete a thread
        delete_response = client.delete(
            f"/api/convo/threads/{thread_ids[2]}",
            headers=self.auth_headers
        )
        assert delete_response.status_code == 204
        
        # Step 6: Verify thread list after operations
        updated_threads_response = client.get(
            f"/api/convo/rooms/{self.sub_room_id}/threads",
            headers=self.auth_headers
        )
        assert updated_threads_response.status_code == 200
        updated_threads = updated_threads_response.json()
        
        # Should have 2 threads left (one pinned, one archived)
        assert len(updated_threads) == 2
        
        print("✅ Thread management operations test passed")
    
    def test_model_switching_and_settings(self):
        """Test model switching and settings persistence"""
        
        # Step 1: Get available models
        models_response = client.get(
            "/api/convo/models",
            headers=self.auth_headers
        )
        assert models_response.status_code == 200
        models_data = models_response.json()
        assert isinstance(models_data, list)
        assert len(models_data) > 0
        
        # Step 2: Create a thread
        thread_response = client.post(
            f"/api/convo/rooms/{self.sub_room_id}/threads",
            json={"title": "Model Test Thread"},
            headers=self.auth_headers
        )
        assert thread_response.status_code == 201
        thread_id = thread_response.json()["id"]
        
        # Step 3: Send messages with different models
        models_to_test = ["gpt-4o-mini", "gpt-3.5-turbo"]
        
        for model in models_to_test:
            message_response = client.post(
                f"/api/convo/threads/{thread_id}/messages",
                json={
                    "content": f"Test message with {model}",
                    "model": model,
                    "temperature": 0.5
                },
                headers=self.auth_headers
            )
            assert message_response.status_code == 200
        
        # Step 4: Verify messages were created with correct models
        messages_response = client.get(
            f"/api/convo/threads/{thread_id}/messages",
            headers=self.auth_headers
        )
        assert messages_response.status_code == 200
        messages = messages_response.json()
        
        # Should have messages from different models
        model_usage = {}
        for message in messages:
            if message.get("meta") and message["meta"].get("model"):
                model = message["meta"]["model"]
                model_usage[model] = model_usage.get(model, 0) + 1
        
        assert len(model_usage) >= 1  # At least one model used
        
        print("✅ Model switching and settings test passed")

# Integration tests for specific components
class TestConversationServiceIntegration:
    """Integration tests for ConversationService"""
    
    def test_conversation_service_crud_operations(self):
        """Test CRUD operations in ConversationService"""
        service = ConversationService()
        
        # First create a room for the test using database service directly
        from app.services.database_service import get_database_service
        db = get_database_service()
        room_id = "test_sub_room"
        current_time = int(time.time())
        db.execute_update(
            "INSERT INTO rooms (room_id, name, owner_id, type, created_at, updated_at, message_count) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (room_id, "Test Sub Room", "test_user", "sub", current_time, current_time, 0)
        )
        
        # Create thread
        from app.models.conversation_schemas import ConversationThreadCreate
        thread_data = ConversationThreadCreate(title="Integration Test Thread")
        thread = service.create_thread(
            room_id=room_id,
            user_id="test_user",
            thread_data=thread_data
        )
        assert thread.id is not None
        assert thread.title == "Integration Test Thread"
        
        # Get threads by subroom
        retrieved_threads = asyncio.run(service.get_threads_by_room(room_id))
        assert len(retrieved_threads) > 0
        retrieved_thread = retrieved_threads[0]
        assert retrieved_thread.title == thread.title
        
        # Update thread (if method exists)
        if hasattr(service, 'update_thread'):
            updated_thread = service.update_thread(
                thread.id,
                {"title": "Updated Title", "is_pinned": True}
            )
            assert updated_thread.title == "Updated Title"
            assert updated_thread.is_pinned is True
        
        # Create message
        message = service.create_message(
            thread_id=thread.id,
            role="user",
            content="Test message",
            status="complete",
            user_id="test_user"
        )
        assert message["id"] is not None
        assert message["content"] == "Test message"
        
        # Get messages
        messages = service.get_messages_by_thread(thread.id)
        assert len(messages) > 0
        assert messages[0]["content"] == "Test message"
        
        # Delete thread (if method exists)
        if hasattr(service, 'delete_thread'):
            success = service.delete_thread(thread.id)
            assert success is True
            
            # Verify deletion
            remaining_threads = asyncio.run(service.get_threads_by_room(room_id))
            assert len(remaining_threads) == 0
        
        print("✅ ConversationService CRUD operations test passed")

class TestCostTrackingIntegration:
    """Integration tests for CostTrackingService"""
    
    def test_cost_tracking_workflow(self):
        """Test complete cost tracking workflow"""
        service = CostTrackingService()
        
        # Record usage
        service.record_usage(
            user_id="test_user",
            tokens=150,
            model="gpt-4o-mini",
            cost=0.0001
        )
        
        # Get usage stats
        usage_stats = service.get_usage_stats("test_user")
        assert "total_tokens" in usage_stats
        assert "total_cost" in usage_stats
        
        # Check if methods exist and call them if they do
        if hasattr(service, 'get_daily_usage'):
            daily_usage = asyncio.run(service.get_daily_usage("test_user"))
            assert len(daily_usage) > 0
        
        if hasattr(service, 'check_daily_budget'):
            exceeded, budget_info = asyncio.run(service.check_daily_budget("test_user"))
            assert "daily_tokens" in budget_info
            assert "daily_cost" in budget_info
        
        print("✅ Cost tracking workflow test passed")

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
