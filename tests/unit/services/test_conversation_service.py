import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import unittest

from app.services.conversation_service import ConversationService
from app.services.token_usage_tracker import TokenUsageTracker
from app.models.conversation_schemas import ConversationThread, ConversationThreadCreate


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.create_thread = MagicMock()
    repo.touch_room = MagicMock()
    repo.list_threads = MagicMock()
    repo.create_message = MagicMock()
    repo.update_message_content = MagicMock()
    repo.search_messages = MagicMock()
    repo.list_messages = MagicMock()
    repo.list_all_messages = MagicMock()
    repo.get_message = MagicMock()
    repo.create_export_job = MagicMock()
    repo.get_export_job = MagicMock()
    repo.update_export_job = MagicMock()
    repo.get_attachment = MagicMock()
    repo.create_attachment = MagicMock()
    repo.get_room_hierarchy = MagicMock()
    repo.list_message_versions = MagicMock()
    return repo

@pytest.fixture
def mock_redis_client():
    return MagicMock()

@pytest.fixture
def conversation_service(monkeypatch, mock_repo, mock_redis_client):
    monkeypatch.setattr("app.services.conversation_service.get_conversation_repository", lambda: mock_repo)
    tracker = TokenUsageTracker(redis_client=mock_redis_client)
    return ConversationService(token_tracker=tracker)

def test_create_thread(conversation_service, mock_repo):
    thread_data = ConversationThreadCreate(title="Test Thread")
    mock_repo.create_thread.return_value = ConversationThread(
        id="thr_abc",
        sub_room_id="sub123",
        user_id="user456",
        title="Test Thread",
        pinned=False,
        archived=False,
        created_at=int(datetime.now(timezone.utc).timestamp()),
        updated_at=int(datetime.now(timezone.utc).timestamp()),
    )

    result = conversation_service.create_thread(room_id="sub123", user_id="user456", thread_data=thread_data)

    mock_repo.create_thread.assert_called_once_with("sub123", "user456", "Test Thread")
    mock_repo.touch_room.assert_called_once_with("sub123")
    assert result.title == "Test Thread"


def test_get_threads_by_room_with_filters(conversation_service, mock_repo):
    mock_repo.list_threads.return_value = asyncio.sleep(0, [])
    asyncio.run(conversation_service.get_threads_by_room(room_id="sub123", query="search", pinned=True, archived=False))

    mock_repo.list_threads.assert_called_once_with("sub123", query_text="search", pinned=True, archived=False)

def test_increment_token_usage(conversation_service, mock_redis_client):
    mock_redis_client.incrby.return_value = 100

    new_usage = conversation_service.increment_token_usage("user123", 100)

    mock_redis_client.incrby.assert_called_once_with(unittest.mock.ANY, 100)
    mock_redis_client.expire.assert_called_once_with(unittest.mock.ANY, 86400)
    assert new_usage == 100

def test_create_new_message_version(conversation_service, mock_repo):
    """
    Test that creating a new version of a message correctly sets the parentId.
    """
    original_message = {
        "id": "msg_orig", "thread_id": "thr_1", "role": "user", "content": "Original", "meta": {}
    }
    # Mock the get_message_by_id call
    conversation_service.get_message_by_id = MagicMock(return_value=original_message)
    # Mock the create_message call to just return its input
    conversation_service.create_message = MagicMock(side_effect=lambda **kwargs: kwargs)

    new_message = conversation_service.create_new_message_version("msg_orig", "New content")

    conversation_service.get_message_by_id.assert_called_once_with("msg_orig")

    # Check that create_message was called with the correct parameters
    args, kwargs = conversation_service.create_message.call_args
    assert kwargs["content"] == "New content"
    assert kwargs["meta"]["parentId"] == "msg_orig"

def test_create_message(conversation_service, mock_repo):
    """
    Test that create_message constructs the correct SQL query.
    """
    now_dt = datetime.now(timezone.utc)
    mock_repo.create_message.return_value = {
        "id": "msg_123",
        "thread_id": "thr_123",
        "role": "user",
        "content": "Hello",
        "model": "gpt-4o",
        "status": "complete",
        "created_at": int(now_dt.timestamp()),
        "meta": {"some": "data", "model": "gpt-4o"}
    }
    result = conversation_service.create_message(
        thread_id="thr_123",
        role="user",
        content="Hello",
        status="complete",
        model="gpt-4o",
        meta={"some": "data"}
    )

    mock_repo.create_message.assert_called_once_with(
        "thr_123",
        "user",
        "Hello",
        status="complete",
        model="gpt-4o",
        meta={"some": "data"},
        user_id="anonymous",
    )
    assert result["thread_id"] == "thr_123"
    assert result["meta"]["model"] == "gpt-4o"
