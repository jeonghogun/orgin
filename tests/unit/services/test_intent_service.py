import pytest

from app.services.intent_service import IntentService


class DummyLLMService:
    def get_provider(self):
        raise AssertionError("LLM should not be called for heuristic intents")


@pytest.fixture
def intent_service():
    return IntentService(llm_service=DummyLLMService())


@pytest.mark.asyncio
async def test_classify_intent_name_set(intent_service):
    result = await intent_service.classify_intent("내 이름은 호건이야 기억해줘")
    assert result["intent"] == "name_set"
    assert result["entities"].get("name") == "호건"


@pytest.mark.asyncio
async def test_classify_intent_time(intent_service):
    result = await intent_service.classify_intent("지금 시간 알려줘")
    assert result["intent"] == "time"


@pytest.mark.asyncio
async def test_classify_intent_weather(intent_service):
    result = await intent_service.classify_intent("오늘 서울 날씨 어때?")
    assert result["intent"] == "weather"
    assert result["entities"].get("location") == "서울"


@pytest.mark.asyncio
async def test_classify_intent_name_get(intent_service):
    result = await intent_service.classify_intent("내 이름이 뭐야?")
    assert result["intent"] == "name_get"
