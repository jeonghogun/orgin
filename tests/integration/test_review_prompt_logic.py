import json
from unittest.mock import patch

from app.tasks.review_tasks import (
    run_initial_panel_turn,
    run_rebuttal_turn,
    run_synthesis_turn,
    run_resolution_turn,
    generate_consolidated_report,
)
from app.services.llm_strategy import ProviderPanelistConfig

# Mock panelist configurations that will be returned by the mocked strategy service
mock_panelists = [
    ProviderPanelistConfig(provider="openai", persona="Optimist", model="gpt-4"),
    ProviderPanelistConfig(provider="claude", persona="Skeptic", model="claude-3"),
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
        "key_takeaway": "This is the key takeaway.",
        "arguments": ["Argument 1"],
        "risks": ["Risk 1"],
        "opportunities": ["Opportunity 1"],
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
    assert "Topic: Test Topic" in prompt_r1
    assert '"round": 1' in prompt_r1

    rebuttal_kwargs = mock_rebuttal_delay.call_args.kwargs
    turn_1_outputs_for_r2 = rebuttal_kwargs["turn_1_outputs"]
    panel_history_for_r2 = rebuttal_kwargs["panel_history"]
    all_metrics_after_r1 = rebuttal_kwargs["all_metrics"]
    assert panel_history_for_r2["Optimist"]["1"]["round"] == 1

    # --- ROUND 2: Rebuttal Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_2_output = {
        "round": 2,
        "agreements": ["Agree with Arg 1"],
        "disagreements": [{"point": "Risk 1 is overstated", "reasoning": "Because..."}],
        "additions": [{"point": "Consider X", "reasoning": "Because..."}],
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
    assert "Rebuttal Round" in prompt_r2
    assert "Key Takeaway: This is the key takeaway." in prompt_r2

    synthesis_kwargs = mock_synthesis_delay.call_args.kwargs
    turn_1_outputs_for_r3 = synthesis_kwargs["turn_1_outputs"]
    turn_2_outputs_for_r3 = synthesis_kwargs["turn_2_outputs"]
    panel_history_for_r3 = synthesis_kwargs["panel_history"]
    all_metrics_after_r2 = synthesis_kwargs["all_metrics"]

    # --- ROUND 3: Synthesis Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_3_output = {
        "round": 3,
        "executive_summary": "Final summary.",
        "conclusion": "Detailed conclusion.",
        "recommendations": ["Do this."],
        "no_new_arguments": False,
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_3_output), {"total_tokens": 30})

    with patch("app.tasks.review_tasks.run_resolution_turn.delay") as mock_resolution_delay:
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
    assert "Synthesis Round" in prompt_r3
    assert "Point: Risk 1 is overstated" in prompt_r3

    resolution_kwargs = mock_resolution_delay.call_args.kwargs
    panel_history_for_r4 = resolution_kwargs["panel_history"]
    round_3_outputs_for_r4 = resolution_kwargs["round_3_outputs"]
    all_metrics_after_r3 = resolution_kwargs["all_metrics"]

    # --- ROUND 4: Final Alignment Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_4_output = {
        "round": 4,
        "no_new_arguments": False,
        "final_position": "Final stance.",
        "consensus_highlights": ["Consensus 1"],
        "open_questions": ["Question 1"],
        "next_steps": ["Next 1"],
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_4_output), {"total_tokens": 35})

    with patch("app.tasks.review_tasks.generate_consolidated_report.delay") as mock_report_delay:
        run_resolution_turn(
            review_id="test_review_1",
            review_room_id="test_room_1",
            panel_history=panel_history_for_r4,
            round_3_outputs=round_3_outputs_for_r4,
            all_metrics=all_metrics_after_r3,
            successful_panelists=mock_panelist_dicts,
            trace_id="test-trace-id",
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r4 = mock_llm_instance.invoke_sync.call_args.kwargs["user_prompt"]
    assert "Final Alignment Round" in prompt_r4

    report_kwargs = mock_report_delay.call_args.kwargs
    panel_history_for_final = report_kwargs["panel_history"]
    all_metrics_for_final = report_kwargs["all_metrics"]
    executed_rounds_for_final = report_kwargs["executed_rounds"]
    assert executed_rounds_for_final[-1] == 4

    # --- FINAL REPORT ---
    mock_llm_instance.invoke_sync.reset_mock()
    final_report_output = {
        "executive_summary": "Final report.",
        "strongest_consensus": [],
        "remaining_disagreements": [],
        "recommendations": ["Final recommendation."],
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(final_report_output), {"total_tokens": 40})

    generate_consolidated_report(
        review_id="test_review_1",
        panel_history=panel_history_for_final,
        all_metrics=all_metrics_for_final,
        executed_rounds=executed_rounds_for_final,
        trace_id="test-trace-id",
    )

    assert mock_llm_instance.invoke_sync.call_count == 1
    system_prompt_final = mock_llm_instance.invoke_sync.call_args.kwargs["system_prompt"]
    assert "You are the Chief Editor" in system_prompt_final

    mock_storage.save_final_report.assert_called_once()
