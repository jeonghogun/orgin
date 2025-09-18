import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import unittest

from app.services.conversation_service import ConversationService
from app.models.conversation_schemas import ConversationThreadCreate

@pytest.fixture
def mock_db_service():
    db = MagicMock()
    db.execute_query = MagicMock()
    db.execute_update = MagicMock()
    db.execute_returning = MagicMock()
    return db

@pytest.fixture
def mock_redis_client():
    return MagicMock()

@pytest.fixture
def conversation_service(monkeypatch, mock_db_service, mock_redis_client):
    monkeypatch.setattr("app.services.conversation_service.get_database_service", lambda: mock_db_service)
    monkeypatch.setattr("redis.from_url", lambda url: mock_redis_client)
    return ConversationService()

def test_create_thread(conversation_service, mock_db_service):
    thread_data = ConversationThreadCreate(title="Test Thread")
    now_dt = datetime.now(timezone.utc)
    mock_db_service.execute_returning.return_value = [{
        "id": "thr_abc",
        "sub_room_id": "sub123",
        "user_id": "user456",
        "title": "Test Thread",
        "pinned": False,
        "archived": False,
        "created_at": now_dt,
        "updated_at": now_dt,
    }]

    result = conversation_service.create_thread(room_id="sub123", user_id="user456", thread_data=thread_data)

    mock_db_service.execute_returning.assert_called_once()
    insert_args, _ = mock_db_service.execute_returning.call_args
    insert_query, insert_params = insert_args[0], insert_args[1]

    assert "INSERT INTO conversation_threads" in insert_query
    assert insert_params[1] == "sub123"
    mock_db_service.execute_update.assert_called_once()
    assert result.title == "Test Thread"

def test_get_threads_by_room_with_filters(conversation_service, mock_db_service):
    mock_db_service.execute_query.return_value = []
    import asyncio
    asyncio.run(conversation_service.get_threads_by_room(room_id="sub123", query="search", pinned=True, archived=False))

    mock_db_service.execute_query.assert_called_once()
    args, _ = mock_db_service.execute_query.call_args
    query, params = args[0], args[1]

    assert "ILIKE %s" in query
    assert "pinned = %s" in query
    assert "archived = %s" in query
    assert params == ("sub123", "%search%", True, False)

def test_increment_token_usage(conversation_service, mock_redis_client):
    mock_redis_client.incrby.return_value = 100

    new_usage = conversation_service.increment_token_usage("user123", 100)

    mock_redis_client.incrby.assert_called_once_with(unittest.mock.ANY, 100)
    mock_redis_client.expire.assert_called_once_with(unittest.mock.ANY, 86400)
    assert new_usage == 100

def test_create_new_message_version(conversation_service, mock_db_service):
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

def test_create_message(conversation_service, mock_db_service):
    """
    Test that create_message constructs the correct SQL query.
    """
    now_dt = datetime.now(timezone.utc)
    mock_db_service.execute_returning.return_value = [{
        "id": "msg_123",
        "thread_id": "thr_123",
        "role": "user",
        "content": "Hello",
        "model": "gpt-4o",
        "status": "complete",
        "created_at": now_dt,
        "meta": {"some": "data", "model": "gpt-4o"}
    }]
    result = conversation_service.create_message(
        thread_id="thr_123",
        role="user",
        content="Hello",
        status="complete",
        model="gpt-4o",
        meta={"some": "data"}
    )

    mock_db_service.execute_returning.assert_called()
    call_args, _ = mock_db_service.execute_returning.call_args
    insert_query, params = call_args[0], call_args[1]

    assert "INSERT INTO conversation_messages" in insert_query
    assert "(id, thread_id, user_id, role, content, model, status, meta)" in insert_query
    assert params[1] == "thr_123"
    assert params[2] == "anonymous"
    assert params[3] == "user"
    assert params[4] == "Hello"
    mock_db_service.execute_update.assert_called()
    assert result["thread_id"] == "thr_123"
    assert result["meta"]["model"] == "gpt-4o"
