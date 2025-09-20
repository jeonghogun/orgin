import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import RoomType
from app.models.schemas import Room
from app.services.review_service import ReviewService


def test_create_interactive_review_generates_ai_title(monkeypatch):
    storage_mock = MagicMock()
    storage_mock.get_room.return_value = SimpleNamespace(room_id="sub_room", type=RoomType.SUB)
    storage_mock.get_messages.return_value = [
        SimpleNamespace(role="user", content="이번 주 런칭 점검 계획을 정리합시다."),
        SimpleNamespace(role="assistant", content="런칭 점검 체크리스트를 업데이트했습니다."),
    ]

    def create_room_side_effect(**kwargs):
        return Room(
            room_id=kwargs["room_id"],
            name=kwargs["name"],
            owner_id=kwargs["owner_id"],
            type=kwargs["room_type"].value,
            parent_id=kwargs.get("parent_id"),
            created_at=0,
            updated_at=0,
            message_count=0,
        )

    storage_mock.create_room.side_effect = create_room_side_effect
    storage_mock.save_review_meta.return_value = None
    storage_mock.save_message.return_value = None

    review_service = ReviewService(storage_mock)
    review_service.start_review_process = AsyncMock()

    mock_llm_service = SimpleNamespace()
    mock_llm_service.invoke = AsyncMock(return_value=('{"title": "마케팅 런칭 최종 점검"}', {}))
    mock_llm_service.get_available_providers = lambda: ["openai"]

    monkeypatch.setattr("app.services.review_service.get_llm_service", lambda: mock_llm_service)
    monkeypatch.setattr(
        "app.services.review_service.llm_strategy_service.get_default_panelists",
        lambda: [SimpleNamespace(provider="openai", persona="GPT", model="gpt-4")],
    )
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("app.services.review_service.redis_pubsub_manager.publish_sync", lambda *args, **kwargs: None)

    response = asyncio.run(
        review_service.create_interactive_review(
            parent_id="sub_room",
            topic="런칭 점검",
            user_id="user123",
        )
    )

    assert response.status == "created"
    created_name = storage_mock.create_room.call_args.kwargs["name"]
    assert created_name == "검토: 마케팅 런칭 최종 점검"

    saved_meta = storage_mock.save_review_meta.call_args.args[0]
    assert saved_meta.topic == "마케팅 런칭 최종 점검"

    saved_message = storage_mock.save_message.call_args.args[0]
    assert "마케팅 런칭 최종 점검" in saved_message.content

    review_service.start_review_process.assert_awaited_once()
