import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.fact_extractor_service import FactExtractorService
from app.services.fact_types import FactType, FactSensitivity

@pytest.fixture
def mock_llm_service():
    return MagicMock()

@pytest.fixture
def fact_extractor_service(mock_llm_service):
    return FactExtractorService(llm_service=mock_llm_service)

def test_normalize_value_simple(fact_extractor_service):
    assert fact_extractor_service.normalize_value(FactType.HOBBY, "  Playing Guitar! ") == "playing guitar"

def test_normalize_value_mbti(fact_extractor_service):
    assert fact_extractor_service.normalize_value(FactType.MBTI, "intj") == "INTJ"
    assert fact_extractor_service.normalize_value(FactType.MBTI, " eNfP-t ") == "ENFP"

def test_get_sensitivity(fact_extractor_service):
    assert fact_extractor_service.get_sensitivity(FactType.USER_NAME) == FactSensitivity.PRIVATE
    assert fact_extractor_service.get_sensitivity(FactType.HOBBY) == FactSensitivity.PUBLIC

@pytest.mark.asyncio
async def test_extract_facts_from_message_success(fact_extractor_service, mock_llm_service):
    mock_provider = MagicMock()
    mock_provider.invoke = AsyncMock(return_value=('{"facts": [{"type": "user_name", "value": "test", "confidence": 0.9}]}', {}))
    mock_llm_service.get_provider.return_value = mock_provider
    facts = await fact_extractor_service.extract_facts_from_message("My name is test", "test_msg_id")
    assert len(facts) == 1
    assert facts[0]['type'] == "user_name"


@pytest.mark.asyncio
async def test_extract_facts_from_message_fallback_patterns(fact_extractor_service, mock_llm_service):
    mock_provider = MagicMock()
    mock_provider.invoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    mock_llm_service.get_provider.return_value = mock_provider

    facts = await fact_extractor_service.extract_facts_from_message("내 이름은 호건이야", "msg_fallback")

    assert len(facts) == 1
    assert facts[0]["type"] == FactType.USER_NAME.value
    assert facts[0]["value"] == "호건"
