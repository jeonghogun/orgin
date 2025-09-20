import unittest
from unittest.mock import patch, MagicMock, call

from app.tasks.review_tasks import run_initial_panel_turn, ProviderPanelistConfig

class TestReviewTasks(unittest.TestCase):

    @patch('app.tasks.review_tasks.redis_pubsub_manager')
    @patch('app.tasks.review_tasks.storage_service')
    @patch('app.tasks.review_tasks.run_rebuttal_turn.delay')
    @patch('app.tasks.review_tasks._process_turn_results')
    @patch('app.tasks.review_tasks.run_panelist_turn')
    @patch('app.tasks.review_tasks.prompt_service')
    @patch('app.tasks.review_tasks.llm_strategy_service')
    @patch('app.tasks.review_tasks.redis.from_url')
    def test_fault_tolerance_fallback_to_openai(
        self,
        mock_redis,
        mock_llm_strategy,
        mock_prompt_service,
        mock_run_panelist_turn,
        mock_process_results,
        mock_run_rebuttal,
        mock_storage,
        mock_redis_pubsub,
    ):
        """
        Tests that if a non-OpenAI panelist fails, the task retries that turn
        with the OpenAI provider as a fallback, as per the README's design.
        """
        # --- Arrange ---
        # Mock Celery task context
        mock_task = MagicMock()
        mock_task.llm_service = MagicMock()

        # Mock panelist configurations
        openai_config = ProviderPanelistConfig(provider='openai', persona='GPT-4o', model='gpt-4o-mini')
        claude_config = ProviderPanelistConfig(provider='claude', persona='Claude 3 Haiku', model='claude-3-haiku')
        panel_configs = [openai_config, claude_config]
        mock_llm_strategy.get_default_panelists.return_value = panel_configs

        # Mock prompt service
        mock_prompt_service.get_prompt.return_value = "Test Prompt"

        # Define a robust side_effect function to prevent StopIteration on retries
        def run_panelist_turn_side_effect(llm_service, p_config, prompt, request_id):
            if p_config.provider == 'claude':
                return (p_config, ValueError("Claude API Error"))
            elif p_config.provider == 'openai':
                if p_config.persona == claude_config.persona:  # This is the fallback call
                    return (p_config, ("Fallback Success", {"metric": 2}))
                else:  # This is the initial successful call
                    return (p_config, ("OpenAI Success", {"metric": 1}))
            raise Exception("Unexpected call to mock_run_panelist_turn")

        mock_run_panelist_turn.side_effect = run_panelist_turn_side_effect

        # Mock the return value of _process_turn_results to prevent unpack errors
        mock_process_results.return_value = ({}, [], [])

        # --- Act ---
        run_initial_panel_turn.apply(
            (
                "review123", "room123", "Test Topic", "Test Instruction", None, "trace123"
            ),
            instance=mock_task
        )

        # --- Assert ---
        # 1. Check that run_panelist_turn was called three times
        self.assertEqual(mock_run_panelist_turn.call_count, 3, "Expected 3 calls: initial OpenAI, initial Claude, and fallback for Claude.")

        # 2. Check the arguments of the third (fallback) call
        fallback_call_args = mock_run_panelist_turn.call_args_list[2]
        fallback_config_arg = fallback_call_args.args[1]
        self.assertEqual(fallback_config_arg.provider, 'openai', "Fallback provider should be openai.")
        self.assertEqual(
            fallback_config_arg.persona,
            claude_config.persona,
            "Fallback should retain the original persona.",
        )

        # 3. Check that the final results passed to _process_turn_results are correct
        self.assertTrue(mock_process_results.called, "_process_turn_results should have been called.")
        process_results_args = mock_process_results.call_args.args[3] # The 'results' argument

        # The results should contain the successful OpenAI turn and the successful fallback turn
        self.assertEqual(len(process_results_args), 2)
        final_personas = [res[0].persona for res in process_results_args]
        self.assertIn('GPT-4o', final_personas)
        self.assertIn('Claude 3 Haiku', final_personas)

        # Check that the content of the skeptic's result is the fallback success message
        claude_result = next(res for res in process_results_args if res[0].persona == claude_config.persona)
        self.assertEqual(claude_result[1][0], "Fallback Success")


if __name__ == '__main__':
    unittest.main()
