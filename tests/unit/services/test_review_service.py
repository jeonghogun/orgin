import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import RoomType
from app.models.schemas import Room
from app.services.review_service import ReviewService, CLARIFYING_FALLBACK_PROMPT


def _create_room_from_kwargs(**kwargs):
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


def test_create_interactive_review_generates_ai_title(monkeypatch):
    storage_mock = MagicMock()
    storage_mock.get_room.return_value = SimpleNamespace(room_id="sub_room", type=RoomType.SUB)
    storage_mock.get_messages.return_value = [
        SimpleNamespace(role="assistant", user_id="system", content="**핵심 요약:** 날씨, 파일 업로드"),
        SimpleNamespace(role="user", user_id="user123", content="이번 주 런칭 점검 계획을 정리합시다."),
        SimpleNamespace(role="assistant", user_id="assistant", content="런칭 점검 체크리스트를 업데이트했습니다."),
        SimpleNamespace(role="assistant", user_id="assistant", content="점심 메뉴도 정해야겠네요."),
    ]

    storage_mock.create_room.side_effect = _create_room_from_kwargs
    storage_mock.save_review_meta.return_value = None
    storage_mock.save_message.return_value = None

    review_service = ReviewService(storage_mock)
    review_service.start_review_process = AsyncMock()

    mock_llm_service = SimpleNamespace()
    mock_llm_service.invoke = AsyncMock(return_value=('{"title": "마케팅 런칭 최종 점검"}', {}))
    mock_llm_service.get_available_providers = lambda: ["openai"]

    captured_prompt = {}

    async def fake_generate(llm, *, fallback_topic, conversation, history=None):
        captured_prompt["conversation"] = conversation
        captured_prompt["fallback"] = fallback_topic
        captured_prompt["history"] = history
        return "마케팅 런칭 최종 점검"

    monkeypatch.setattr("app.services.review_service.get_llm_service", lambda: mock_llm_service)
    monkeypatch.setattr(
        "app.services.review_service.llm_strategy_service.get_default_panelists",
        lambda: [SimpleNamespace(provider="openai", persona="GPT", model="gpt-4")],
    )
    monkeypatch.setattr(review_service, "_generate_review_topic_title", AsyncMock(side_effect=fake_generate))

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
    assert "[참고 맥락]" in saved_meta.instruction
    assert "**핵심 요약:**" not in saved_meta.instruction

    saved_message = storage_mock.save_message.call_args.args[0]
    assert "마케팅 런칭 최종 점검" in saved_message.content

    review_service.start_review_process.assert_awaited_once()

    assert "**핵심 요약:**" not in captured_prompt["conversation"]
    assert "점심 메뉴" not in captured_prompt["conversation"]
    assert "런칭 점검" in captured_prompt["conversation"]


def test_create_interactive_review_uses_topic_when_no_context(monkeypatch):
    storage_mock = MagicMock()
    storage_mock.get_room.return_value = SimpleNamespace(room_id="sub_room", type=RoomType.SUB)
    storage_mock.get_messages.return_value = [
        SimpleNamespace(role="assistant", user_id="system", content="**핵심 요약:** 파일 업로드 로그"),
        SimpleNamespace(role="user", user_id="user123", content="오늘 날씨가 좋네요."),
    ]

    storage_mock.create_room.side_effect = _create_room_from_kwargs
    storage_mock.save_review_meta.return_value = None
    storage_mock.save_message.return_value = None

    review_service = ReviewService(storage_mock)
    review_service.start_review_process = AsyncMock()

    mock_llm_service = SimpleNamespace()
    mock_llm_service.invoke = AsyncMock(return_value=('{"title": "AI 전략 재정비"}', {}))
    mock_llm_service.get_available_providers = lambda: ["openai"]

    captured_prompt = {}

    async def fake_generate(llm, *, fallback_topic, conversation, history=None):
        captured_prompt["conversation"] = conversation
        captured_prompt["fallback"] = fallback_topic
        return fallback_topic

    monkeypatch.setattr("app.services.review_service.get_llm_service", lambda: mock_llm_service)
    monkeypatch.setattr(
        "app.services.review_service.llm_strategy_service.get_default_panelists",
        lambda: [SimpleNamespace(provider="openai", persona="GPT", model="gpt-4")],
    )
    monkeypatch.setattr(review_service, "_generate_review_topic_title", AsyncMock(side_effect=fake_generate))

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("app.services.review_service.redis_pubsub_manager.publish_sync", lambda *args, **kwargs: None)

    response = asyncio.run(
        review_service.create_interactive_review(
            parent_id="sub_room",
            topic="AI 전략 재정비",
            user_id="user123",
        )
    )

    assert response.status == "created"
    assert captured_prompt["conversation"] == ""
    assert captured_prompt["fallback"] == "AI 전략 재정비"


def test_create_interactive_review_requests_more_detail_for_short_topic(monkeypatch):
    storage_mock = MagicMock()
    storage_mock.get_room.return_value = SimpleNamespace(room_id="sub_room", type=RoomType.SUB)
    storage_mock.get_messages.return_value = []

    review_service = ReviewService(storage_mock)
    review_service.start_review_process = AsyncMock()

    mock_llm_service = SimpleNamespace()
    mock_llm_service.invoke = AsyncMock(return_value=("{\"question\": \"좀 더 구체적으로 알고 싶은 영역이 있으신가요?\"}", {}))
    mock_llm_service.get_available_providers = lambda: ["openai"]

    monkeypatch.setattr("app.services.review_service.get_llm_service", lambda: mock_llm_service)

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("app.services.review_service.realtime_service.publish", AsyncMock())

    history = [
        {"role": "assistant", "content": "어떤 주제로 검토를 진행할까요?"},
        {"role": "user", "content": "AI의 미래"},
    ]

    response = asyncio.run(
        review_service.create_interactive_review(
            parent_id="sub_room",
            topic="AI의 미래",
            user_id="user123",
            history=history,
        )
    )

    assert response.status == "needs_more_context"
    assert "구체적으로" in (response.question or "")
    assert "프로젝트" not in (response.question or "")
    review_service.start_review_process.assert_not_called()


def test_create_interactive_review_asks_question_for_vague_topic(monkeypatch):
    storage_mock = MagicMock()
    storage_mock.get_room.return_value = SimpleNamespace(room_id="sub_room", type=RoomType.SUB)
    storage_mock.get_messages.return_value = []

    review_service = ReviewService(storage_mock)

    mock_llm_service = SimpleNamespace()
    mock_llm_service.invoke = AsyncMock(return_value=("{\"question\": \"어떤 관점에서 보고 싶으신가요?\"}", {}))
    mock_llm_service.get_available_providers = lambda: ["openai"]

    monkeypatch.setattr("app.services.review_service.get_llm_service", lambda: mock_llm_service)

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("app.services.review_service.realtime_service.publish", AsyncMock())

    response = asyncio.run(
        review_service.create_interactive_review(
            parent_id="sub_room",
            topic="AI",
            user_id="user123",
        )
    )

    assert response.status == "needs_more_context"
    assert "관점" in response.question


def test_create_interactive_review_uses_parent_context_when_topic_short(monkeypatch):
    storage_mock = MagicMock()
    storage_mock.get_room.return_value = SimpleNamespace(room_id="sub_room", type=RoomType.SUB)
    storage_mock.get_messages.return_value = [
        SimpleNamespace(role="user", user_id="u1", content="내일 서울 비 예보 대응 전략을 다시 정리해야 합니다."),
        SimpleNamespace(role="assistant", user_id="assistant", content="자료 요약본을 업데이트했습니다."),
    ]

    storage_mock.create_room.side_effect = _create_room_from_kwargs
    storage_mock.save_review_meta.return_value = None
    storage_mock.save_message.return_value = None

    review_service = ReviewService(storage_mock)
    review_service.start_review_process = AsyncMock()

    mock_llm_service = SimpleNamespace()
    mock_llm_service.invoke = AsyncMock(return_value=("{\"title\": \"서울 비 예보 대응\"}", {}))
    mock_llm_service.get_available_providers = lambda: ["openai"]

    monkeypatch.setattr("app.services.review_service.get_llm_service", lambda: mock_llm_service)
    monkeypatch.setattr(
        "app.services.review_service.llm_strategy_service.get_default_panelists",
        lambda: [SimpleNamespace(provider="openai", persona="GPT", model="gpt-4")],
    )

    captured_prompt = {}

    async def fake_generate(*args, **kwargs):
        captured_prompt.update(kwargs)
        return "서울 비 예보 대응"

    monkeypatch.setattr(review_service, "_generate_review_topic_title", AsyncMock(side_effect=fake_generate))

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("app.services.review_service.redis_pubsub_manager.publish_sync", lambda *a, **k: None)

    response = asyncio.run(
        review_service.create_interactive_review(
            parent_id="sub_room",
            topic="네",
            user_id="user123",
        )
    )

    assert response.status == "created"
    assert captured_prompt.get("conversation")
    review_service.start_review_process.assert_awaited_once()


def test_create_interactive_review_limits_clarifying_questions(monkeypatch):
    storage_mock = MagicMock()
    storage_mock.get_room.return_value = SimpleNamespace(room_id="sub_room", type=RoomType.SUB)
    storage_mock.get_messages.return_value = []

    storage_mock.create_room.side_effect = _create_room_from_kwargs
    storage_mock.save_review_meta.return_value = None
    storage_mock.save_message.return_value = None

    review_service = ReviewService(storage_mock)
    review_service.start_review_process = AsyncMock()

    mock_llm_service = SimpleNamespace()
    mock_llm_service.invoke = AsyncMock(return_value=("{\"title\": \"임시 검토 주제\"}", {}))
    mock_llm_service.get_available_providers = lambda: ["openai"]

    monkeypatch.setattr("app.services.review_service.get_llm_service", lambda: mock_llm_service)
    monkeypatch.setattr(
        "app.services.review_service.llm_strategy_service.get_default_panelists",
        lambda: [SimpleNamespace(provider="openai", persona="GPT", model="gpt-4")],
    )
    monkeypatch.setattr(review_service, "_generate_review_topic_title", AsyncMock(return_value="임시 검토 주제"))

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("app.services.review_service.redis_pubsub_manager.publish_sync", lambda *a, **k: None)
    monkeypatch.setattr("app.services.review_service.realtime_service.publish", AsyncMock())

    history = [
        {"role": "assistant", "content": "어떤 내용을 검토하고 싶으세요?"},
        {"role": "user", "content": "몰라요"},
        {"role": "assistant", "content": "조금 더 구체적으로 말씀해 주실 수 있을까요?"},
        {"role": "user", "content": "아직 생각이 안 났어요"},
    ]

    response = asyncio.run(
        review_service.create_interactive_review(
            parent_id="sub_room",
            topic="?",
            user_id="user123",
            history=history,
        )
    )

    assert response.status == "needs_more_context"
    assert response.question == CLARIFYING_FALLBACK_PROMPT
    review_service.start_review_process.assert_not_called()

    history_with_confirmation = history + [
        {"role": "assistant", "content": CLARIFYING_FALLBACK_PROMPT},
        {"role": "user", "content": "네 진행해주세요"},
    ]

    response_after_confirmation = asyncio.run(
        review_service.create_interactive_review(
            parent_id="sub_room",
            topic="?",
            user_id="user123",
            history=history_with_confirmation,
        )
    )

    assert response_after_confirmation.status == "created"
    review_service.start_review_process.assert_awaited_once()
