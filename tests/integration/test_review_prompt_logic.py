import pytest
import json
from unittest.mock import patch, MagicMock, call

from app.tasks.review_tasks import (
    run_initial_panel_turn,
    run_rebuttal_turn,
    run_synthesis_turn,
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
@patch("app.tasks.base_task.LLMService") # Patch the LLMService where it's instantiated
@patch("app.tasks.review_tasks.storage_service")
@patch("app.tasks.review_tasks.redis_pubsub_manager")
def test_full_review_prompt_logic(mock_pubsub, mock_storage, mock_llm_service_class, mock_llm_strategy, mock_redis):
    """
    Tests the entire review flow by calling the tasks directly.
    This version patches the LLMService at the source to avoid mocking 'self'.
    """
    # --- 1. Configure all mocks ---
    mock_llm_strategy.get_default_panelists.return_value = mock_panelists
    mock_redis.from_url.return_value.get.return_value = "0"
    mock_redis.from_url.return_value.close.return_value = None

    # Get a handle to the instance of the mocked LLMService
    mock_llm_instance = mock_llm_service_class.return_value

    # --- ROUND 1: Initial Turn ---
    round_1_output = {
        "round": 1, "key_takeaway": "This is the key takeaway.", "arguments": ["Argument 1"],
        "risks": ["Risk 1"], "opportunities": ["Opportunity 1"]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_1_output), {"total_tokens": 10})

    with patch("app.tasks.review_tasks.run_rebuttal_turn.delay") as mock_rebuttal_delay:
        # Call the task without 'self'. Celery handles it.
        run_initial_panel_turn(
            review_id="test_review_1", review_room_id="test_room_1", topic="Test Topic",
            instruction="Test Instruction", panelists_override=None, trace_id="test-trace-id"
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r1 = mock_llm_instance.invoke_sync.call_args_list[0].kwargs['user_prompt']
    assert "Topic: Test Topic" in prompt_r1
    assert '"round": 1' in prompt_r1

    rebuttal_args = mock_rebuttal_delay.call_args.args
    turn_1_outputs_for_r2 = rebuttal_args[2]

    # --- ROUND 2: Rebuttal Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_2_output = {
        "round": 2, "agreements": ["Agree with Arg 1"],
        "disagreements": [{"point": "Risk 1 is overstated", "reasoning": "Because..."}],
        "additions": [{"point": "Consider X", "reasoning": "Because..."}]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_2_output), {"total_tokens": 20})

    with patch("app.tasks.review_tasks.run_synthesis_turn.delay") as mock_synthesis_delay:
        run_rebuttal_turn(
            review_id="test_review_1", review_room_id="test_room_1",
            turn_1_outputs=turn_1_outputs_for_r2,
            all_metrics=[[{"total_tokens": 10}, {"total_tokens": 10}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r2 = mock_llm_instance.invoke_sync.call_args_list[0].kwargs['user_prompt']
    assert "Rebuttal Round" in prompt_r2
    assert "Key Takeaway: This is the key takeaway." in prompt_r2

    synthesis_args = mock_synthesis_delay.call_args.args
    turn_1_outputs_for_r3, turn_2_outputs_for_r3 = synthesis_args[2], synthesis_args[3]

    # --- ROUND 3: Synthesis Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_3_output = {
        "round": 3, "executive_summary": "Final summary.", "conclusion": "Detailed conclusion.",
        "recommendations": ["Do this."]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_3_output), {"total_tokens": 30})

    with patch("app.tasks.review_tasks.generate_consolidated_report.delay") as mock_report_delay:
        run_synthesis_turn(
            review_id="test_review_1", review_room_id="test_room_1",
            turn_1_outputs=turn_1_outputs_for_r3, turn_2_outputs=turn_2_outputs_for_r3,
            all_metrics=[[{"total_tokens": 10}], [{"total_tokens": 20}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r3 = mock_llm_instance.invoke_sync.call_args.kwargs['user_prompt']
    assert "Synthesis Round" in prompt_r3
    assert "Point: Risk 1 is overstated" in prompt_r3

    report_args = mock_report_delay.call_args.args
    turn_3_outputs_for_final = report_args[1]

    # --- FINAL REPORT ---
    mock_llm_instance.invoke_sync.reset_mock()
    final_report_output = {
        "executive_summary": "Final report.", "strongest_consensus": [],
        "remaining_disagreements": [], "recommendations": ["Final recommendation."]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(final_report_output), {"total_tokens": 40})

    generate_consolidated_report(
        review_id="test_review_1", turn_3_outputs=turn_3_outputs_for_final,
        all_metrics=[], trace_id="test-trace-id"
    )

    assert mock_llm_instance.invoke_sync.call_count == 1
    system_prompt_final = mock_llm_instance.invoke_sync.call_args.kwargs['system_prompt']
    assert "You are the Chief Editor" in system_prompt_final

    mock_storage.save_final_report.assert_called_once()
