import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.user_fact_service import UserFactService
from app.services.fact_types import FactType

@pytest.fixture
def mock_db_service_for_concurrency():
    """
    A mock DB service that can simulate the state changes
    that might occur during concurrent execution.
    """
    mock = MagicMock()
    # Let the first call to find a conflict return nothing,
    # but subsequent calls find the fact inserted by the other coroutine.
    mock.execute_query.side_effect = [
        [], # First call for coroutine 1 (conflict check)
        [], # First call for coroutine 2 (conflict check)
        [{'id': 'fact_1'}], # Second call for coroutine 2 (duplicate check)
    ]
    mock.execute_update = MagicMock()
    return mock

@pytest.mark.asyncio
async def test_save_fact_concurrency_no_duplicates(mock_db_service_for_concurrency, mock_audit_service, mock_secret_provider):
    """
    Simulates two facts arriving at roughly the same time.
    The service should be robust enough to only insert one of them
    if they are duplicates, avoiding race conditions.
    """
    user_fact_service = UserFactService(
        db_service=mock_db_service_for_concurrency,
        audit_service=mock_audit_service,
        secret_provider=mock_secret_provider
    )

    fact1 = {'type': FactType.JOB.value, 'value': 'Developer', 'confidence': 0.9}
    fact2 = {'type': FactType.JOB.value, 'value': 'Software Engineer', 'confidence': 0.92}

    # These two facts will have the same normalized value
    normalized_value = "developer"

    with patch.object(user_fact_service, '_insert_fact', new_callable=AsyncMock) as mock_insert:
        # Simulate running both save operations concurrently
        await asyncio.gather(
            user_fact_service.save_fact(
                "concurrent_user", fact1, normalized_value, "msg1", "public", "room1"
            ),
            user_fact_service.save_fact(
                "concurrent_user", fact2, normalized_value, "msg2", "public", "room1"
            )
        )

        # Even though they ran concurrently, only one should have been inserted
        # because the second one would have found the first one upon its duplicate check.
        # This relies on the transaction isolation level of the database in a real scenario.
        # In our mock, we simulated this with the side_effect of execute_query.
        assert mock_insert.call_count == 1
