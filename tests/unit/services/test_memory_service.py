import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.memory_service import MemoryService
from app.config.settings import settings

# A simple mock for the Message model for testing purposes
class MockMessage:
    def __init__(self, message_id, content, timestamp, score=0.0):
        self.message_id = message_id
        self.content = content
        self.timestamp = timestamp
        self.score = score

    def __getitem__(self, key):
        return getattr(self, key)

@pytest.fixture
def mock_llm_service():
    return AsyncMock()

@pytest.fixture
def mock_db_service():
    return MagicMock()

@pytest.fixture
def mock_secret_provider():
    provider = MagicMock()
    provider.get.return_value = "test_key"
    return provider

@pytest.fixture
def memory_service(mock_db_service, mock_llm_service, mock_secret_provider):
    return MemoryService(mock_db_service, mock_llm_service, mock_secret_provider)

def test_normalize_scores():
    service = MemoryService(MagicMock(), MagicMock(), MagicMock())
    results = [
        {'score': 10},
        {'score': 20},
        {'score': 30},
    ]
    normalized = service._normalize_scores(results)
    assert [r['score'] for r in normalized] == [0.0, 0.5, 1.0]

def test_merge_and_score(memory_service):
    settings.HYBRID_BM25_WEIGHT = 0.6
    settings.HYBRID_VEC_WEIGHT = 0.4

    bm25 = [{'message_id': '1', 'score': 10}, {'message_id': '2', 'score': 20}]
    vector = [{'message_id': '2', 'score': 50}, {'message_id': '3', 'score': 100}]

    merged = memory_service._merge_and_score(bm25, vector)

    # After normalization, scores are:
    # bm25: id1=0.0, id2=1.0
    # vector: id2=0.0, id3=1.0
    # Merged scores:
    # id1: 0.0 * 0.6 = 0.0
    # id2: (1.0 * 0.6) + (0.0 * 0.4) = 0.6
    # id3: 1.0 * 0.4 = 0.4

    scores = {r['message_id']: r['score'] for r in merged}
    assert scores['1'] == pytest.approx(0.0)
    assert scores['2'] == pytest.approx(0.6)
    assert scores['3'] == pytest.approx(0.4)

def test_time_decay(memory_service):
    from datetime import datetime, timezone
    now = int(datetime.now(timezone.utc).timestamp())

    results = [
        {'score': 1.0, 'timestamp': now}, # age=0, decay=1.0
        {'score': 1.0, 'timestamp': now - (60*60*24*30)} # age=30, decay=exp(-0.03*30)=0.406
    ]

    settings.TIME_DECAY_LAMBDA = 0.03
    decayed = memory_service._apply_time_decay(results)

    assert decayed[0]['score'] == pytest.approx(1.0)
    assert decayed[1]['score'] == pytest.approx(0.406, abs=0.01)


@pytest.mark.anyio
async def test_get_relevant_memories_hybrid(memory_service, monkeypatch):
    """Test the main hybrid retrieval method, mocking the candidate generation."""
    # Mock the internal methods that perform DB queries
    mock_bm25 = AsyncMock(return_value=[
        {'message_id': 'bm25_1', 'content': 'BM25 hit 1', 'score': 0.8, 'timestamp': 100}
    ])
    mock_vector = AsyncMock(return_value=[
        {'message_id': 'vec_1', 'content': 'Vector hit 1', 'score': 0.9, 'timestamp': 200}
    ])
    monkeypatch.setattr(memory_service, '_bm25_candidates', mock_bm25)
    monkeypatch.setattr(memory_service, '_vector_candidates', mock_vector)

    # Mock settings
    monkeypatch.setattr(settings, 'TIME_DECAY_ENABLED', False)
    monkeypatch.setattr(settings, 'RERANK_ENABLED', False)

    results = await memory_service.get_relevant_memories_hybrid("test", ["room1"], "user1")

    # Assert that the internal methods were called
    mock_bm25.assert_awaited_once()
    mock_vector.assert_awaited_once()

    # Assert that we got results back
    assert len(results) == 2
    assert results[0].message_id == 'vec_1' # Higher score after merge
    assert results[1].message_id == 'bm25_1'


@pytest.mark.anyio
async def test_get_user_profile_found(memory_service, mock_db_service):
    """Test getting a user profile that exists."""
    mock_db_service.execute_query.return_value = [{
        "user_id": "test_user",
        "role": "user",
        "name": "Test User",
        "preferences": "{}",
        "conversation_style": "neutral",
        "interests": [],
        "created_at": 123,
        "updated_at": 123
    }]

    profile = await memory_service.get_user_profile("test_user")

    mock_db_service.execute_query.assert_called_once()
    assert profile is not None
    assert profile.user_id == "test_user"
    assert profile.name == "Test User"
    mock_db_service.execute_update.assert_not_called()


@pytest.mark.anyio
async def test_get_user_profile_not_found_creates_new(memory_service, mock_db_service):
    """Test that a new user profile is created if not found."""
    # First call to find profile returns nothing
    mock_db_service.execute_query.side_effect = [
        [], # First call for get
        [{   # Second call inside get_user_profile after creation
            "user_id": "new_user", "role": "user", "name": "New User",
            "preferences": "{}", "conversation_style": "neutral", "interests": [],
            "created_at": 123, "updated_at": 123
        }]
    ]

    profile = await memory_service.get_user_profile("new_user")

    assert mock_db_service.execute_query.call_count == 2
    mock_db_service.execute_update.assert_called_once() # Asserts that the INSERT was called
    assert profile is not None
    assert profile.user_id == "new_user"
