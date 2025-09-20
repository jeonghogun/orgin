import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.tasks.review_tasks import (
    run_initial_panel_turn,
    run_rebuttal_turn,
    run_synthesis_turn,
    generate_consolidated_report,
)
from app.services.llm_strategy import ProviderPanelistConfig

# Mock panelist configurations that will be returned by the mocked strategy service
mock_panelists = [
    ProviderPanelistConfig(provider="openai", persona="GPT-4o", model="gpt-4"),
    ProviderPanelistConfig(provider="claude", persona="Claude 3 Haiku", model="claude-3"),
]
mock_panelist_dicts = [p.model_dump() for p in mock_panelists]


@patch("app.tasks.review_tasks.redis")
@patch("app.tasks.review_tasks.llm_strategy_service")
@patch("app.tasks.base_task.LLMService")
@patch("app.tasks.review_tasks.storage_service")
@patch("app.tasks.review_tasks.redis_pubsub_manager")
def test_full_review_prompt_logic(
    mock_pubsub,
    mock_storage,
    mock_llm_service_class,
    mock_llm_strategy,
    mock_redis,
):
    """Exercise the full multi-round review flow with patched dependencies."""
    mock_llm_strategy.get_default_panelists.return_value = mock_panelists
    mock_redis.from_url.return_value.get.return_value = "0"
    mock_redis.from_url.return_value.close.return_value = None

    mock_llm_instance = mock_llm_service_class.return_value

    # --- ROUND 1: Initial Turn ---
    round_1_output = {
        "round": 1,
        "panelist": "GPT-4o",
        "message": "우리는 30일 파일럿으로 빠르게 사용자 반응을 확인해 봅시다.",
        "key_takeaway": "30일 파일럿으로 학습 시작.",
        "references": [],
        "no_new_arguments": False,
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_1_output), {"total_tokens": 10})

    with patch("app.tasks.review_tasks.run_rebuttal_turn.delay") as mock_rebuttal_delay:
        run_initial_panel_turn(
            review_id="test_review_1",
            review_room_id="test_room_1",
            topic="Test Topic",
            instruction="Test Instruction",
            panelists_override=None,
            trace_id="test-trace-id",
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r1 = mock_llm_instance.invoke_sync.call_args_list[0].kwargs["user_prompt"]
    assert "Round 1 – Independent Perspective" in prompt_r1
    assert "JSON은 아래 스키마" in prompt_r1

    rebuttal_kwargs = mock_rebuttal_delay.call_args.kwargs
    turn_1_outputs_for_r2 = rebuttal_kwargs["turn_1_outputs"]
    panel_history_for_r2 = rebuttal_kwargs["panel_history"]
    all_metrics_after_r1 = rebuttal_kwargs["all_metrics"]
    assert panel_history_for_r2["GPT-4o"]["1"]["round"] == 1

    # --- ROUND 2: Rebuttal Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_2_output = {
        "round": 2,
        "panelist": "GPT-4o",
        "message": "Claude 3 Haiku가 지적한 통제 포인트에 동의하지만, 속도는 그대로 유지하죠.",
        "key_takeaway": "통제를 붙여도 속도는 유지.",
        "references": [
            {
                "panelist": "Claude 3 Haiku",
                "round": 1,
                "quote": "통제 경계를 명확히",
                "stance": "support",
            },
            {
                "panelist": "Gemini 1.5 Flash",
                "round": 1,
                "quote": "실험 범위를 넓히자",
                "stance": "build",
            },
        ],
        "no_new_arguments": False,
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_2_output), {"total_tokens": 20})

    with patch("app.tasks.review_tasks.run_synthesis_turn.delay") as mock_synthesis_delay:
        run_rebuttal_turn(
            review_id="test_review_1",
            review_room_id="test_room_1",
            turn_1_outputs=turn_1_outputs_for_r2,
            panel_history=panel_history_for_r2,
            all_metrics=all_metrics_after_r1,
            successful_panelists=mock_panelist_dicts,
            trace_id="test-trace-id",
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r2 = mock_llm_instance.invoke_sync.call_args_list[0].kwargs["user_prompt"]
    assert "Round 2 – Response & Reflection (GPT-4o)" in prompt_r2
    assert "references 배열" in prompt_r2

    synthesis_kwargs = mock_synthesis_delay.call_args.kwargs
    turn_1_outputs_for_r3 = synthesis_kwargs["turn_1_outputs"]
    turn_2_outputs_for_r3 = synthesis_kwargs["turn_2_outputs"]
    panel_history_for_r3 = synthesis_kwargs["panel_history"]
    all_metrics_after_r2 = synthesis_kwargs["all_metrics"]

    # --- ROUND 3: Synthesis Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_3_output = {
        "round": 3,
        "panelist": "GPT-4o",
        "message": "이제 30일 파일럿 뒤 60일 확장 검증으로 이어가며 합의한 체크리스트를 적용합시다.",
        "key_takeaway": "30일→60일 로드맵 정리.",
        "references": [
            {
                "panelist": "Claude 3 Haiku",
                "round": 2,
                "quote": "체크리스트 통과",
                "stance": "support",
            }
        ],
        "no_new_arguments": False,
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_3_output), {"total_tokens": 30})

    with patch("app.tasks.review_tasks.generate_consolidated_report.delay") as mock_report_delay:
        run_synthesis_turn(
            review_id="test_review_1",
            review_room_id="test_room_1",
            turn_1_outputs=turn_1_outputs_for_r3,
            turn_2_outputs=turn_2_outputs_for_r3,
            panel_history=panel_history_for_r3,
            all_metrics=all_metrics_after_r2,
            successful_panelists=mock_panelist_dicts,
            trace_id="test-trace-id",
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r3 = mock_llm_instance.invoke_sync.call_args.kwargs["user_prompt"]
    assert "Round 3 – Joint Synthesis (GPT-4o)" in prompt_r3
    assert "세 패널이 함께" in prompt_r3

    report_kwargs = mock_report_delay.call_args.kwargs
    panel_history_for_final = report_kwargs["panel_history"]
    all_metrics_for_final = report_kwargs["all_metrics"]
    executed_rounds_for_final = report_kwargs["executed_rounds"]
    assert executed_rounds_for_final[-1] == 3

    # --- FINAL REPORT ---
    mock_llm_instance.invoke_sync.reset_mock()
    final_report_output = {
        "executive_summary": "Final report.",
        "strongest_consensus": ["Agree on fast pilot"],
        "remaining_disagreements": [],
        "recommendations": ["Final recommendation."],
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(final_report_output), {"total_tokens": 40})

    mock_storage.get_review_meta.return_value = SimpleNamespace(
        review_id="test_review_1",
        room_id="review_room_1",
        topic="테스트 토픽",
        instruction="Test Instruction",
        status="pending",
        total_rounds=4,
        created_at=0,
    )

    review_room = SimpleNamespace(room_id="review_room_1", parent_id="sub_room_1", owner_id="user123")
    sub_room = SimpleNamespace(room_id="sub_room_1", parent_id="main_room_1", owner_id="user123")
    main_room = SimpleNamespace(room_id="main_room_1", parent_id=None, owner_id="user123")

    def room_lookup(room_id):
        return {
            "review_room_1": review_room,
            "sub_room_1": sub_room,
            "main_room_1": main_room,
        }.get(room_id)

    mock_storage.get_room.side_effect = room_lookup
    mock_storage.save_message.reset_mock()

    with patch("app.tasks.review_tasks.realtime_service") as mock_realtime, patch(
        "app.tasks.review_tasks.get_memory_service"
    ) as mock_get_memory_service:
        mock_realtime.publish = AsyncMock()
        mock_memory_service = mock_get_memory_service.return_value
        mock_memory_service.record_review_outcome = AsyncMock()

        generate_consolidated_report(
            review_id="test_review_1",
            panel_history=panel_history_for_final,
            all_metrics=all_metrics_for_final,
            executed_rounds=executed_rounds_for_final,
            trace_id="test-trace-id",
        )

        mock_realtime.publish.assert_awaited()
        mock_memory_service.record_review_outcome.assert_awaited_once()
        memory_args = mock_memory_service.record_review_outcome.await_args.kwargs
        assert memory_args["main_room_id"] == "main_room_1"
        assert memory_args["topic"] == "테스트 토픽"

    parent_messages = [
        call.args[0]
        for call in mock_storage.save_message.call_args_list
        if getattr(call.args[0], "room_id", None) == "sub_room_1"
    ]
    assert parent_messages, "Expected a handoff message to the parent sub-room."
    assert "검토 결과 동기화" in parent_messages[-1].content
    assert "메인룸 장기 기억" in parent_messages[-1].content

    assert mock_llm_instance.invoke_sync.call_count == 1
    system_prompt_final = mock_llm_instance.invoke_sync.call_args.kwargs["system_prompt"]
    assert "You are the Chief Editor" in system_prompt_final

    mock_storage.save_final_report.assert_called_once()
