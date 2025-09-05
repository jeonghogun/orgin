import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.user_fact_service import UserFactService
from app.services.fact_types import FactType

@pytest.fixture
def mock_db_service():
    mock = MagicMock()
    mock.execute_query = MagicMock(return_value=[])
    mock.execute_update = MagicMock()
    return mock

@pytest.fixture
def mock_audit_service():
    service = MagicMock()
    service.log = AsyncMock()
    return service

@pytest.fixture
def mock_secret_provider():
    provider = MagicMock()
    provider.get.return_value = "test-key"
    return provider

@pytest.fixture
def user_fact_service(mock_db_service, mock_audit_service, mock_secret_provider):
    return UserFactService(
        db_service=mock_db_service,
        audit_service=mock_audit_service,
        secret_provider=mock_secret_provider
    )

@pytest.mark.asyncio
@patch("app.tasks.fact_tasks.request_user_clarification_task.delay")
async def test_save_fact_conflict_review(mock_celery_task, user_fact_service, mock_db_service):
    """
    Tests that a conflict for a single-value fact with similar confidence
    marks both for review and triggers a Celery task.
    """
    fact = {'type': FactType.MBTI.value, 'value': 'ENFP', 'confidence': 0.85}
    user_id, room_id = "test_user", "test_room"

    mock_db_service.execute_query.side_effect = [
        [], [{'id': 'old_fact_id', 'confidence': 0.9}]
    ]
    with patch.object(user_fact_service, '_insert_fact', new_callable=AsyncMock) as mock_insert:
        mock_insert.return_value = "new_fact_id"

        await user_fact_service.save_fact(
            user_id=user_id, fact=fact, normalized_value="enfp",
            source_message_id="test_msg", sensitivity="public", room_id=room_id
        )

        mock_db_service.execute_update.assert_any_call(
            "UPDATE user_facts SET pending_review = TRUE WHERE id = %s", ('old_fact_id',)
        )
        mock_insert.assert_called_once_with(
            user_id, fact, "enfp", "test_msg", "public", is_latest=False, pending_review=True
        )
        mock_celery_task.assert_called_once_with(
            user_id=user_id, room_id=room_id,
            fact_type=FactType.MBTI.value, fact_ids=['old_fact_id', 'new_fact_id']
        )
