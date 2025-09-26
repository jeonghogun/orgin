import asyncio
from types import SimpleNamespace

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


class FakeMemoryService:
    def __init__(self, profile=None):
        self._profile = profile

    async def get_user_profile(self, user_id):
        return self._profile


def test_initialize_sub_room_with_related_context(monkeypatch):
    storage = FakeStorage(
        [
            SimpleNamespace(role="user", content="Deep Learning의 윤리적 이슈를 논의해 봅시다."),
            SimpleNamespace(role="assistant", content="좋습니다. 특히 deep learning 모델의 투명성을 짚어볼게요."),
            SimpleNamespace(role="user", content="날씨도 좋고 집중하기 좋네요."),
        ]
    )
    profile = SimpleNamespace(name="미나", conversation_style="analytical", interests=["AI", "윤리"])
    service = SubRoomContextService(storage_service=storage, memory_service=FakeMemoryService(profile))

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
        assert message.content.startswith("'Deep Learning' 세부룸을 시작합니다.")
        assert "윤리적 이슈" in message.content
        assert "날씨" not in message.content, "Irrelevant chatter should be filtered out"
        assert "사용자 페르소나 참고" in message.content
        assert "미나" in message.content
        assert storage.saved_messages, "Message should be persisted"
        assert not captured_alerts, "No fallback alert should fire when highlights exist"

    asyncio.run(runner())


def test_initialize_sub_room_fallback_when_no_related_context(monkeypatch):
    storage = FakeStorage(
        [
            SimpleNamespace(role="user", content="오늘 할 일은 무엇일까요?"),
            SimpleNamespace(role="assistant", content="파일 업로드가 완료되었습니다."),
        ]
    )
    service = SubRoomContextService(storage_service=storage, memory_service=FakeMemoryService())

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
        assert message.content.startswith("'Quantum' 세부룸이 열렸습니다.")
        assert "반가워요" in message.content
        assert storage.saved_messages, "Fallback message should still be persisted"
        assert captured_alerts, "Alert must be sent when fallback is used"

    asyncio.run(runner())
