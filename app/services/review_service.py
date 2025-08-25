"""
Review Service - Orchestrates the multi-agent review process
"""
import asyncio
import logging
from typing import List, Dict, Any

from app.services.storage_service import storage_service
from app.services.llm_service import llm_service
from app.utils.helpers import get_current_timestamp
from app.models.schemas import ReviewEvent

logger = logging.getLogger(__name__)

# Define the personas for the review process as per the spec
PERSONAS = ["OpenAI GPT-4", "Google Gemini", "Anthropic Claude"]


class ReviewService:
    """Orchestrates the multi-agent, multi-round review process."""

    def __init__(self):
        """Initialize the review service."""
        self.storage = storage_service
        self.llm = llm_service

    async def execute_review(self, review_id: str):
        """
        Executes the full 3-round review process for a given review ID.
        This is a long-running task.
        """
        logger.info(f"Starting review process for review_id: {review_id}")
        try:
            review_meta = await self.storage.get_review_meta(review_id)
            if not review_meta:
                logger.error(f"Review with ID {review_id} not found.")
                return

            await self.storage.log_review_event(
                self._create_event(review_id, "start", content="Review process started.")
            )

            # --- Round 1: Independent Analysis ---
            await self.storage.update_review(review_id, {"current_round": 1})
            await self.storage.log_review_event(
                self._create_event(review_id, "round_start", round_num=1, content="Round 1: Independent Analysis")
            )

            round_1_instruction = f"Here is the topic for review: '{review_meta.topic}'. Please provide your independent, expert analysis based on this instruction: '{review_meta.instruction}'"
            round_1_tasks = [
                self._run_panel_analysis(review_id, 1, persona, round_1_instruction)
                for persona in PERSONAS
            ]
            round_1_results = await asyncio.gather(*round_1_tasks)

            # --- Round 2: Critique and Refinement ---
            await self.storage.update_review(review_id, {"current_round": 2})
            await self.storage.log_review_event(
                self._create_event(review_id, "round_start", round_num=2, content="Round 2: Critique and Refinement")
            )

            round_2_tasks = [
                self._run_critique_round(review_id, 2, persona, round_1_results)
                for persona in PERSONAS
            ]
            round_2_results = await asyncio.gather(*round_2_tasks)

            # --- Round 3: Final Conclusion ---
            await self.storage.update_review(review_id, {"current_round": 3})
            await self.storage.log_review_event(
                self._create_event(review_id, "round_start", round_num=3, content="Round 3: Final Conclusion")
            )

            round_3_tasks = [
                self._run_conclusion_round(review_id, 3, persona, round_1_results, round_2_results)
                for persona in PERSONAS
            ]
            round_3_results = await asyncio.gather(*round_3_tasks)

            # --- Final Report Generation ---
            await self._generate_and_save_final_report(review_id, review_meta.topic, round_3_results)

            await self.storage.log_review_event(
                self._create_event(review_id, "finish", content="Review process completed.")
            )
            await self.storage.update_review(
                review_id, {"status": "completed", "completed_at": get_current_timestamp()}
            )
            logger.info(f"Review process for review_id: {review_id} has completed.")

        except Exception as e:
            logger.error(f"An error occurred during the review process for {review_id}: {e}", exc_info=True)
            await self.storage.update_review(review_id, {"status": "failed"})
            await self.storage.log_review_event(
                self._create_event(review_id, "error", content=f"An error occurred: {e}")
            )

    async def _run_panel_analysis(self, review_id: str, round_num: int, persona: str, instruction: str) -> Dict[str, Any]:
        """Runs analysis for a single panelist and logs the event."""
        await self.storage.log_review_event(
            self._create_event(review_id, "panel_start", round_num, persona, content="Analysis started.")
        )

        try:
            # Note: For now, we use the same LLM provider for all personas.
            # This can be extended to use different providers based on the persona name.
            provider = self.llm.get_provider("openai")
            request_id = f"{review_id}-{round_num}-{persona.replace(' ', '_')}"

            response = await provider.invoke(
                model="gpt-4-turbo",  # Using a powerful model for analysis
                system_prompt=f"You are an AI assistant acting as '{persona}'. Provide a detailed, critical, and constructive analysis. Respond in JSON.",
                user_prompt=instruction,
                request_id=request_id,
                response_format="json",
            )

            content = response.get("content", "{}")
            await self.storage.log_review_event(
                self._create_event(review_id, "panel_finish", round_num, persona, content=content)
            )
            return {"persona": persona, "content": content}
        except Exception as e:
            logger.error(f"Panel analysis failed for {persona} in review {review_id}: {e}")
            await self.storage.log_review_event(
                self._create_event(review_id, "panel_error", round_num, persona, content=str(e))
            )
            return {"persona": persona, "content": {"error": str(e)}}

    async def _run_critique_round(self, review_id: str, round_num: int, persona: str, previous_round_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Runs the critique and refinement round for a single panelist."""

        # Prepare the context from the previous round
        other_personas_reports = []
        my_previous_report = ""
        for result in previous_round_results:
            if result["persona"] == persona:
                my_previous_report = result["content"]
            else:
                other_personas_reports.append(f"- **{result['persona']}'s Analysis:**\n{result['content']}\n")

        instruction = f"""Here are the analyses from the other experts in Round 1:

{''.join(other_personas_reports)}

Here is your own initial analysis from Round 1:
{my_previous_report}

Please review all analyses. Critique the other perspectives, identify any blind spots (including your own), and provide a refined, more robust version of your analysis.
"""
        return await self._run_panel_analysis(review_id, round_num, persona, instruction)

    async def _run_conclusion_round(self, review_id: str, round_num: int, persona: str, round_1_results: List[Dict[str, Any]], round_2_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Runs the final conclusion round for a single panelist."""

        # Find the persona's own previous reports
        my_round_1_report = next((r["content"] for r in round_1_results if r["persona"] == persona), "N/A")
        my_round_2_report = next((r["content"] for r in round_2_results if r["persona"] == persona), "N/A")

        instruction = f"""This is the final round. You have seen the initial analyses and the refined arguments from all experts.

Your initial analysis (Round 1):
{my_round_1_report}

Your refined analysis (Round 2):
{my_round_2_report}

Based on the entire discussion, please provide your final, conclusive analysis. Synthesize the key insights, state your final position clearly, and offer actionable recommendations. This will be your last word on the topic.
"""
        return await self._run_panel_analysis(review_id, round_num, persona, instruction)

    async def _generate_and_save_final_report(self, review_id: str, topic: str, round_3_results: List[Dict[str, Any]]):
        """Generates the final consolidated report and saves it."""
        logger.info(f"Generating final report for review {review_id}")

        final_conclusions = [
            f"**{result['persona']}'s Final Conclusion:**\n{result['content']}\n"
            for result in round_3_results
        ]

        prompt = f"""The multi-round AI debate on the topic '{topic}' has concluded. Here are the final statements from each expert AI panelist:

{''.join(final_conclusions)}

Please synthesize these final conclusions into a single, cohesive, and easy-to-read final report. The report should have an executive summary, a summary of each perspective, and a final recommendation.
"""

        # Using a general-purpose LLM call for the final summary
        provider = self.llm.get_provider("openai")
        request_id = f"{review_id}-final-report"
        response = await provider.invoke(
            model="gpt-4-turbo",
            system_prompt="You are a master summarizer, tasked with creating a final, consolidated report from a series of AI expert conclusions.",
            user_prompt=prompt,
            request_id=request_id,
            response_format="json",  # Assuming the final report is also structured JSON
        )

        final_report_data = response.get("content", "{}")

        await self.storage.save_final_report(review_id, final_report_data)
        logger.info(f"Final report for review {review_id} has been generated and saved.")

    def _create_event(self, review_id: str, event_type: str, round_num: int = None, actor: str = None, content: str = None) -> Dict[str, Any]:
        """Helper to create a ReviewEvent dictionary."""
        event = ReviewEvent(
            ts=get_current_timestamp(),
            type=event_type,
            review_id=review_id,
            round=round_num,
            actor=actor,
            content=content,
        )
        return event.model_dump(exclude_none=True)


# Singleton instance of the review service
review_service = ReviewService()
