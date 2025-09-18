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

<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
    rebuttal_kwargs = mock_rebuttal_delay.call_args.kwargs
<<<<<<< ours
    turn_1_outputs_for_r2 = rebuttal_kwargs['turn_1_outputs']
    panel_history_after_r1 = rebuttal_kwargs['panel_history']
    assert panel_history_after_r1['Optimist']['1']['round'] == 1
=======
    turn_1_outputs_for_r2 = rebuttal_kwargs["turn_1_outputs"]
    panel_history_for_r2 = rebuttal_kwargs["panel_history"]
    metrics_for_r2 = rebuttal_kwargs["all_metrics"]
>>>>>>> theirs
=======
    rebuttal_args = mock_rebuttal_delay.call_args.args
    turn_1_outputs_for_r2 = rebuttal_args[2]
>>>>>>> theirs
=======
    rebuttal_kwargs = mock_rebuttal_delay.call_args.kwargs
    turn_1_outputs_for_r2 = rebuttal_kwargs["turn_1_outputs"]
    panel_history_for_r2 = rebuttal_kwargs["panel_history"]
    metrics_for_r2 = rebuttal_kwargs["all_metrics"]
>>>>>>> theirs
=======
    rebuttal_args = mock_rebuttal_delay.call_args.args
    turn_1_outputs_for_r2 = rebuttal_args[2]
>>>>>>> theirs

    # --- ROUND 2: Rebuttal Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_2_output = {
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
        "round": 2,
<<<<<<< ours
        "no_new_arguments": False,
=======
>>>>>>> theirs
        "agreements": ["Agree with Arg 1"],
=======
        "round": 2, "agreements": ["Agree with Arg 1"],
>>>>>>> theirs
=======
        "round": 2,
        "agreements": ["Agree with Arg 1"],
>>>>>>> theirs
=======
        "round": 2, "agreements": ["Agree with Arg 1"],
>>>>>>> theirs
        "disagreements": [{"point": "Risk 1 is overstated", "reasoning": "Because..."}],
        "additions": [{"point": "Consider X", "reasoning": "Because..."}]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_2_output), {"total_tokens": 20})

    with patch("app.tasks.review_tasks.run_synthesis_turn.delay") as mock_synthesis_delay:
        run_rebuttal_turn(
            review_id="test_review_1", review_room_id="test_room_1",
            turn_1_outputs=turn_1_outputs_for_r2,
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
            panel_history=panel_history_after_r1,
            all_metrics=[[{"total_tokens": 10}, {"total_tokens": 10}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
=======
=======
>>>>>>> theirs
            panel_history=panel_history_for_r2,
            all_metrics=metrics_for_r2,
            successful_panelists=mock_panelist_dicts,
            trace_id="test-trace-id",
<<<<<<< ours
>>>>>>> theirs
=======
            all_metrics=[[{"total_tokens": 10}, {"total_tokens": 10}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
>>>>>>> theirs
=======
>>>>>>> theirs
=======
            all_metrics=[[{"total_tokens": 10}, {"total_tokens": 10}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
>>>>>>> theirs
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r2 = mock_llm_instance.invoke_sync.call_args_list[0].kwargs['user_prompt']
    assert "Rebuttal Round" in prompt_r2
    assert "Key Takeaway: This is the key takeaway." in prompt_r2

<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
    synthesis_kwargs = mock_synthesis_delay.call_args.kwargs
<<<<<<< ours
    turn_1_outputs_for_r3 = synthesis_kwargs['turn_1_outputs']
    turn_2_outputs_for_r3 = synthesis_kwargs['turn_2_outputs']
    panel_history_after_r2 = synthesis_kwargs['panel_history']
    assert panel_history_after_r2['Optimist']['2']['round'] == 2
=======
=======
    synthesis_kwargs = mock_synthesis_delay.call_args.kwargs
>>>>>>> theirs
    turn_1_outputs_for_r3 = synthesis_kwargs["turn_1_outputs"]
    turn_2_outputs_for_r3 = synthesis_kwargs["turn_2_outputs"]
    panel_history_for_r3 = synthesis_kwargs["panel_history"]
    metrics_for_r3 = synthesis_kwargs["all_metrics"]
<<<<<<< ours
>>>>>>> theirs
=======
    synthesis_args = mock_synthesis_delay.call_args.args
    turn_1_outputs_for_r3, turn_2_outputs_for_r3 = synthesis_args[2], synthesis_args[3]
>>>>>>> theirs
=======
>>>>>>> theirs
=======
    synthesis_args = mock_synthesis_delay.call_args.args
    turn_1_outputs_for_r3, turn_2_outputs_for_r3 = synthesis_args[2], synthesis_args[3]
>>>>>>> theirs

    # --- ROUND 3: Synthesis Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_3_output = {
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
        "round": 3,
<<<<<<< ours
        "no_new_arguments": False,
        "executive_summary": "Final summary.",
        "conclusion": "Detailed conclusion.",
        "recommendations": ["Do this."]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_3_output), {"total_tokens": 30})

    with patch("app.tasks.review_tasks.run_resolution_turn.delay") as mock_round4_delay:
        run_synthesis_turn(
            review_id="test_review_1", review_room_id="test_room_1",
            turn_1_outputs=turn_1_outputs_for_r3,
            turn_2_outputs=turn_2_outputs_for_r3,
            panel_history=panel_history_after_r2,
            all_metrics=[[{"total_tokens": 10}], [{"total_tokens": 20}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
=======
=======
        "round": 3,
>>>>>>> theirs
        "executive_summary": "Final summary.",
        "conclusion": "Detailed conclusion.",
        "recommendations": ["Do this."],
        "no_new_arguments": False,
<<<<<<< ours
=======
        "round": 3, "executive_summary": "Final summary.", "conclusion": "Detailed conclusion.",
        "recommendations": ["Do this."]
>>>>>>> theirs
=======
>>>>>>> theirs
=======
        "round": 3, "executive_summary": "Final summary.", "conclusion": "Detailed conclusion.",
        "recommendations": ["Do this."]
>>>>>>> theirs
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_3_output), {"total_tokens": 30})

    with patch("app.tasks.review_tasks.generate_consolidated_report.delay") as mock_report_delay:
        run_synthesis_turn(
            review_id="test_review_1", review_room_id="test_room_1",
            turn_1_outputs=turn_1_outputs_for_r3, turn_2_outputs=turn_2_outputs_for_r3,
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
=======
>>>>>>> theirs
            panel_history=panel_history_for_r3,
            all_metrics=metrics_for_r3,
            successful_panelists=mock_panelist_dicts,
            trace_id="test-trace-id",
<<<<<<< ours
>>>>>>> theirs
=======
            all_metrics=[[{"total_tokens": 10}], [{"total_tokens": 20}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
>>>>>>> theirs
=======
>>>>>>> theirs
=======
            all_metrics=[[{"total_tokens": 10}], [{"total_tokens": 20}]],
            successful_panelists=mock_panelist_dicts, trace_id="test-trace-id"
>>>>>>> theirs
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r3 = mock_llm_instance.invoke_sync.call_args.kwargs['user_prompt']
    assert "Synthesis Round" in prompt_r3
    assert "Point: Risk 1 is overstated" in prompt_r3

<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
    round4_kwargs = mock_round4_delay.call_args.kwargs
    panel_history_after_r3 = round4_kwargs['panel_history']
    round_3_outputs_for_r4 = round4_kwargs['round_3_outputs']
    assert round_3_outputs_for_r4['Optimist']['round'] == 3

    # --- ROUND 4: Final Alignment Turn ---
    mock_llm_instance.invoke_sync.reset_mock()
    round_4_output = {
        "round": 4,
        "no_new_arguments": False,
        "final_position": "Final stance.",
        "consensus_highlights": ["Consensus 1"],
        "open_questions": ["Question 1"],
        "next_steps": ["Next 1"]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(round_4_output), {"total_tokens": 35})

    with patch("app.tasks.review_tasks.generate_consolidated_report.delay") as mock_report_delay:
        run_resolution_turn(
            review_id="test_review_1",
            review_room_id="test_room_1",
            panel_history=panel_history_after_r3,
            round_3_outputs=round_3_outputs_for_r4,
            all_metrics=[[{"total_tokens": 10}], [{"total_tokens": 20}], [{"total_tokens": 30}]],
            successful_panelists=mock_panelist_dicts,
            trace_id="test-trace-id",
        )

    assert mock_llm_instance.invoke_sync.call_count == 2
    prompt_r4 = mock_llm_instance.invoke_sync.call_args.kwargs['user_prompt']
    assert "Final Alignment Round" in prompt_r4

    report_kwargs = mock_report_delay.call_args.kwargs
    final_panel_history = report_kwargs['panel_history']
    executed_rounds = report_kwargs['executed_rounds']
    assert executed_rounds[-1] == 4
=======
=======
>>>>>>> theirs
    resolution_kwargs = mock_resolution_delay.call_args.kwargs
    panel_history_for_r4 = resolution_kwargs["panel_history"]
    round_3_outputs_for_r4 = resolution_kwargs["round_3_outputs"]
    metrics_for_r4 = resolution_kwargs["all_metrics"]
<<<<<<< ours
>>>>>>> theirs
=======
    report_args = mock_report_delay.call_args.args
    turn_3_outputs_for_final = report_args[1]
>>>>>>> theirs
=======
>>>>>>> theirs
=======
    report_args = mock_report_delay.call_args.args
    turn_3_outputs_for_final = report_args[1]
>>>>>>> theirs

    # --- FINAL REPORT ---
    mock_llm_instance.invoke_sync.reset_mock()
    final_report_output = {
        "executive_summary": "Final report.", "strongest_consensus": [],
        "remaining_disagreements": [], "recommendations": ["Final recommendation."]
    }
    mock_llm_instance.invoke_sync.return_value = (json.dumps(final_report_output), {"total_tokens": 40})

    generate_consolidated_report(
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
        review_id="test_review_1",
<<<<<<< ours
        panel_history=final_panel_history,
        all_metrics=[],
        executed_rounds=executed_rounds,
=======
        panel_history=panel_history_for_final,
        all_metrics=all_metrics_for_final,
        executed_rounds=executed_rounds_for_final,
>>>>>>> theirs
        trace_id="test-trace-id",
=======
        review_id="test_review_1", turn_3_outputs=turn_3_outputs_for_final,
        all_metrics=[], trace_id="test-trace-id"
>>>>>>> theirs
=======
        review_id="test_review_1",
        panel_history=panel_history_for_final,
        all_metrics=all_metrics_for_final,
        executed_rounds=executed_rounds_for_final,
        trace_id="test-trace-id",
>>>>>>> theirs
=======
        review_id="test_review_1", turn_3_outputs=turn_3_outputs_for_final,
        all_metrics=[], trace_id="test-trace-id"
>>>>>>> theirs
    )

    assert mock_llm_instance.invoke_sync.call_count == 1
    system_prompt_final = mock_llm_instance.invoke_sync.call_args.kwargs['system_prompt']
    assert "You are the Chief Editor" in system_prompt_final

    mock_storage.save_final_report.assert_called_once()
