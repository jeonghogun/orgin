import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

pytestmark = pytest.mark.anyio

MOCK_SUB_ROOM_ID = "room_sub_1"

def test_create_and_list_threads(authenticated_client: TestClient):
    response = authenticated_client.post(f"/api/convo/rooms/{MOCK_SUB_ROOM_ID}/threads", json={"title": "Integration Test Thread"})
    assert response.status_code == 201
    created_thread = response.json()
    thread_id = created_thread["id"]

    response = authenticated_client.get(f"/api/convo/rooms/{MOCK_SUB_ROOM_ID}/threads")
    assert response.status_code == 200
    listed_threads = response.json()
    assert any(t["id"] == thread_id for t in listed_threads)

def test_full_message_and_stream_flow(authenticated_client: TestClient):
    res = authenticated_client.post(f"/api/convo/rooms/{MOCK_SUB_ROOM_ID}/threads", json={"title": "SSE Flow Test"})
    assert res.status_code == 201
    thread_id = res.json()["id"]

    async def mock_stream_generator(*args, **kwargs):
        from app.models.conversation_schemas import SSEEvent, SSEDelta, SSEUsage
        yield SSEEvent(event="delta", data=SSEDelta(content="Test "))
        yield SSEEvent(event="delta", data=SSEDelta(content="response."))
        yield SSEEvent(event="usage", data=SSEUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7, cost_usd=0.00001))
        yield SSEEvent(event="done", data={})

    with patch("app.api.routes.conversations.get_llm_adapter") as mock_get_adapter:
        mock_adapter = MagicMock()
        mock_adapter.generate_stream = mock_stream_generator
        mock_get_adapter.return_value = mock_adapter

        res = authenticated_client.post(f"/api/convo/threads/{thread_id}/messages", json={"content": "Hello"})
        assert res.status_code == 200
        assistant_message_id = res.json()["messageId"]

        with authenticated_client.stream("GET", f"/api/convo/messages/{assistant_message_id}/stream") as response:
            assert response.status_code == 200
            response.raise_for_status()

            events = []
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                if line.startswith("data:"):
                    data = json.loads(line.split(":", 1)[1].strip())
                    events.append({"event": event_type, "data": data})

            # Filter out ping events and empty done events
            filtered_events = [e for e in events if e["event"] != "ping" and not (e["event"] == "done" and not e["data"])]
            assert len(filtered_events) == 4
            assert filtered_events[0]["event"] == "delta"
            assert filtered_events[1]["event"] == "delta"
            assert filtered_events[2]["event"] == "usage"
            assert filtered_events[3]["event"] == "done"

    res = authenticated_client.get(f"/api/convo/threads/{thread_id}/messages")
    messages = res.json()
    assistant_message = next((m for m in messages if m["id"] == assistant_message_id), None)
    assert assistant_message is not None
    print(f"DEBUG: assistant_message = {assistant_message}")
    assert assistant_message["content"] == "Test response."
    assert assistant_message["status"] == "complete"
    assert assistant_message["meta"]["total_tokens"] == 7

def test_edit_and_regenerate_flow(authenticated_client: TestClient):
    """
    Tests editing a message and ensuring a new message version is created.
    """
    # 1. Create a thread and an initial user message
    res = authenticated_client.post(f"/api/convo/rooms/{MOCK_SUB_ROOM_ID}/threads", json={"title": "Edit Test"})
    assert res.status_code == 201
    thread_id = res.json()["id"]
    res = authenticated_client.post(f"/api/convo/threads/{thread_id}/messages", json={"content": "Original message"})
    original_assistant_id = res.json()["messageId"]

    # Find the original user message ID
    res = authenticated_client.get(f"/api/convo/threads/{thread_id}/messages")
    messages = res.json()
    original_user_message = next((m for m in messages if m["role"] == "user"), None)
    assert original_user_message is not None
    original_user_message_id = original_user_message["id"]

    # 2. Edit the user message
    res = authenticated_client.patch(f"/api/convo/messages/{original_user_message_id}", json={"content": "Edited message"})
    assert res.status_code == 200
    new_assistant_id = res.json()["messageId"]
    assert new_assistant_id != original_assistant_id

    # 3. Verify the new message versions
    res = authenticated_client.get(f"/api/convo/threads/{thread_id}/messages")
    messages = res.json()

    user_messages = [m for m in messages if m["role"] == "user"]
    assert len(user_messages) == 2 # Original and edited version

    edited_message = next((m for m in user_messages if m["content"] == "Edited message"), None)
    assert edited_message is not None
    assert edited_message["meta"]["parentId"] == original_user_message_id

def test_zip_export(authenticated_client: TestClient):
    """
    Tests the zip export functionality.
    """
    res = authenticated_client.post(f"/api/convo/rooms/{MOCK_SUB_ROOM_ID}/threads", json={"title": "Export Test"})
    assert res.status_code == 201
    thread_id = res.json()["id"]
    authenticated_client.post(f"/api/convo/threads/{thread_id}/messages", json={"content": "Some content for export"})

    res = authenticated_client.get(f"/api/convo/threads/{thread_id}/export?format=zip")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "attachment; filename=" in res.headers["content-disposition"]
    assert res.content is not None

def test_async_export_flow(authenticated_client: TestClient):
    """
    Tests the asynchronous export job flow.
    """
    # 1. Create a thread
    res = authenticated_client.post(f"/api/convo/rooms/{MOCK_SUB_ROOM_ID}/threads", json={"title": "Async Export Test"})
    assert res.status_code == 201
    thread_id = res.json()["id"]

    # 2. Post a job
    res = authenticated_client.post(f"/api/convo/threads/{thread_id}/export/jobs", params={"format": "json"})
    assert res.status_code == 202
    job_id = res.json()["jobId"]
    assert job_id.startswith("exp_")

    # 3. Check job status (since celery is eager, it should be done)
    res = authenticated_client.get(f"/api/convo/export/jobs/{job_id}")
    assert res.status_code == 200
    job = res.json()
    assert job["id"] == job_id
    assert job["status"] == "done"
    assert job["file_url"] is not None

def test_diff_view_flow(authenticated_client: TestClient):
    """
    Tests the message versioning and diffing API endpoints.
    """
    # 1. Create thread and original message
    res = authenticated_client.post(f"/api/convo/rooms/{MOCK_SUB_ROOM_ID}/threads", json={"title": "Diff Test"})
    assert res.status_code == 201
    thread_id = res.json()["id"]
    res = authenticated_client.post(f"/api/convo/threads/{thread_id}/messages", json={"content": "original content"})

    # 2. Get original user message ID
    res = authenticated_client.get(f"/api/convo/threads/{thread_id}/messages")
    orig_user_msg_id = next(m["id"] for m in res.json() if m["role"] == "user")

    # 3. Edit the message
    res = authenticated_client.patch(f"/api/convo/messages/{orig_user_msg_id}", json={"content": "edited content"})
    new_asst_msg_id = res.json()["messageId"]

    # 4. Get versions for the *new* assistant message's parent (the edited user message)
    res = authenticated_client.get(f"/api/convo/threads/{thread_id}/messages")
    edited_user_msg_id = next(m["meta"]["parentId"] for m in res.json() if m["id"] == new_asst_msg_id)

    res = authenticated_client.get(f"/api/convo/messages/{edited_user_msg_id}/versions")
    assert res.status_code == 200
    versions = res.json()
    assert len(versions) == 2
    assert versions[0]["content"] == "original content"
    assert versions[1]["content"] == "edited content"

    # 5. Get the diff
    res = authenticated_client.get(f"/api/convo/messages/{versions[1]['id']}/diff?against={versions[0]['id']}")
    assert res.status_code == 200
    diff = res.json()["diff"]
    assert "- original content" in diff
    assert "+ edited content" in diff
