import asyncio
from types import SimpleNamespace
from typing import Optional

from app.models.schemas import Message
from app.services.sub_room_context_service import (
    SubRoomContextRequest,
    SubRoomContextService,
)


class FakeStorage:
    def __init__(self, messages):
        self._messages = messages
        self.saved_messages = []

    def get_messages(self, room_id):
        return list(self._messages)

    def save_message(self, message: Message):
        self.saved_messages.append(message)


class FakeLLM:
    def __init__(self, responses=None, error: Optional[Exception] = None):
        self._responses = responses or []
        self._error = error
        self.calls = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        if not self._responses:
            raise AssertionError("No responses configured for FakeLLM")
        return self._responses.pop(0), {"total_tokens": 1}


class FakeMemory:
    def __init__(self, profile=None, context=None):
        self._profile = profile
        self._context = context

    async def get_user_profile(self, _user_id):
        return self._profile

    async def get_context(self, _room_id, _user_id):
        return self._context


class DummyModel:
    def __init__(self, payload):
        self._payload = payload

    def model_dump_json(self):
        return self._payload


def test_initialize_sub_room_with_existing_topic(monkeypatch):
    storage = FakeStorage(
        [
            SimpleNamespace(role="user", content="Discussing Deep Learning"),
            SimpleNamespace(role="assistant", content="Deep Learning is the topic"),
        ]
    )
    llm = FakeLLM(responses=["Summarized content"])
    memory = FakeMemory()
    service = SubRoomContextService(storage_service=storage, llm_service=llm, memory_service=memory)

    captured_alerts = []

    async def fake_alert(**kwargs):
        captured_alerts.append(kwargs)

    monkeypatch.setattr(
        "app.services.sub_room_context_service.alert_manager.send_manual_alert",
        fake_alert,
    )

    request = SubRoomContextRequest(
        parent_room_id="parent-1",
        new_room_name="Deep Learning",
        new_room_id="sub-1",
        user_id="user-1",
    )

    async def runner():
        message = await service.initialize_sub_room(request)

        assert message is not None
        assert message.content.startswith("이 세부룸은 메인룸의")
        assert storage.saved_messages, "Message should be persisted"
        assert not captured_alerts, "No fallback alert should fire when summarization succeeds"

    asyncio.run(runner())


def test_initialize_sub_room_fallback_on_llm_failure(monkeypatch):
    storage = FakeStorage([])
    llm = FakeLLM(error=RuntimeError("LLM unavailable"))
    memory = FakeMemory(profile=DummyModel("{}"), context=DummyModel("{}"))
    service = SubRoomContextService(storage_service=storage, llm_service=llm, memory_service=memory)

    captured_alerts = []

    async def fake_alert(**kwargs):
        captured_alerts.append(kwargs)

    monkeypatch.setattr(
        "app.services.sub_room_context_service.alert_manager.send_manual_alert",
        fake_alert,
    )

    request = SubRoomContextRequest(
        parent_room_id="parent-2",
        new_room_name="Quantum",
        new_room_id="sub-2",
        user_id="user-2",
    )

    async def runner():
        message = await service.initialize_sub_room(request)

        assert message is not None
        assert "자유롭게 대화를 이어가 주세요" in message.content
        assert storage.saved_messages, "Fallback message should still be persisted"
        assert captured_alerts, "Alert must be sent when fallback is used"

    asyncio.run(runner())
