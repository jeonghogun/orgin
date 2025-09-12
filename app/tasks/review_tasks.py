import logging
import time
import json
import redis
from datetime import datetime
from typing import List, Dict, Any, Tuple, Union, Optional

from celery import states
from celery.exceptions import Ignore

from app.celery_app import celery_app
from app.config.settings import settings
from app.models.schemas import Message, WebSocketMessage
from app.services.redis_pubsub import redis_pubsub_manager
from app.services.llm_strategy import llm_strategy_service, ProviderPanelistConfig
from app.utils.helpers import generate_id, get_current_timestamp
from app.tasks.base_task import BaseTask
from app.services.llm_service import LLMService
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

class BudgetExceededError(Exception):
    """Custom exception for when a budget is exceeded."""
    pass

def run_panelist_turn(
    llm_service: LLMService,
    panelist_config: ProviderPanelistConfig,
    prompt: str,
    request_id: str
) -> Tuple[ProviderPanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]:
    """Runs a single panelist turn synchronously, with retry logic."""
    try:
        result = llm_service.invoke_sync(
            provider_name=panelist_config.provider,
            model=panelist_config.model,
            system_prompt=panelist_config.system_prompt,
            user_prompt=prompt,
            request_id=f"{request_id}-{panelist_config.provider}",
            response_format="json"
        )
        return panelist_config, result
    except Exception as e:
        logger.error(f"Failed to get response from {panelist_config.provider} for persona {panelist_config.persona}: {e}", exc_info=True)
        return panelist_config, e

def _save_panelist_message(review_room_id: str, content: str, persona: str, round_num: int):
    """Saves a panelist's output as a message in the review room."""
    message = Message(
        message_id=generate_id(),
        room_id=review_room_id,
        role="assistant",
        content=content,
        user_id="assistant",
        timestamp=get_current_timestamp(),
        metadata={"persona": persona, "round": round_num}
    )
    storage_service.save_message(message)

def _check_review_budget(review_id: str, all_metrics: List[List[Dict[str, Any]]]):
    """Checks if the review has exceeded its token budget."""
    if not settings.PER_REVIEW_TOKEN_BUDGET:
        return
    total_tokens = sum(m.get("total_tokens", 0) for r_metrics in all_metrics for m in r_metrics if m)
    if total_tokens > settings.PER_REVIEW_TOKEN_BUDGET:
        error_msg = f"Review {review_id} exceeded token budget of {settings.PER_REVIEW_TOKEN_BUDGET} with {total_tokens} tokens."
        logger.error(error_msg)
        raise BudgetExceededError(error_msg)

def _process_turn_results(
    review_id: str,
    review_room_id: str,
    round_num: int,
    results: List[Tuple[ProviderPanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]],
    all_previous_metrics: List[List[Dict[str, Any]]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[ProviderPanelistConfig]]:
    """Processes results from a single turn, saves messages, and collects metrics."""
    turn_outputs, round_metrics, successful_panelists = {}, [], []
    for panelist_config, result in results:
        persona = panelist_config.persona
        if isinstance(result, BaseException):
            logger.error(f"Panelist {persona} failed in round {round_num}: {result}")
            round_metrics.append({"persona": persona, "success": False, "error": str(result), "provider": panelist_config.provider})
        else:
            content, metrics = result
            try:
                turn_outputs[persona] = json.loads(content)
                round_metrics.append(metrics)
                successful_panelists.append(panelist_config)
                _save_panelist_message(review_room_id, content, persona, round_num)
            except json.JSONDecodeError:
                logger.error(f"Panelist {persona} in round {round_num} returned invalid JSON: {content}")
                round_metrics.append({"persona": persona, "success": False, "error": "Invalid JSON response", "provider": panelist_config.provider})

    _check_review_budget(review_id, all_previous_metrics + [round_metrics])
    return turn_outputs, round_metrics, successful_panelists

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_initial_panel_turn(self: BaseTask, review_id: str, review_room_id: str, topic: str, instruction: str, panelists_override: Optional[List[str]], trace_id: str):
    try:
        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "processing"}).model_dump_json())

        if settings.DAILY_ORG_TOKEN_BUDGET:
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            today_key = f"daily_token_usage:{datetime.utcnow().strftime('%Y-%m-%d')}"
            current_usage = int(redis_client.get(today_key) or 0)
            if current_usage > settings.DAILY_ORG_TOKEN_BUDGET:
                raise BudgetExceededError(f"Daily token budget of {settings.DAILY_ORG_TOKEN_BUDGET} exceeded.")
            redis_client.close()

        panel_configs = llm_strategy_service.get_default_panelists()
        if panelists_override:
            panel_configs = [p for p in panel_configs if p.provider in panelists_override]

        prompt = f"""Topic: {topic}
Instruction: {instruction}

Provide your independent analysis of the topic, **prioritizing the user's specific instruction above.**
- Be realistic and logical.
- Provide clear reasoning, evidence, pros/cons, and possible implications.
- Do not assume what other panelists will say.
- Your output must be in the specified JSON format.
- The JSON schema you must adhere to is:
  {{
    "round": 1,
    "key_takeaway": "A brief summary of the main finding.",
    "arguments": [
      "Core argument 1 (with reasoning)",
      "Core argument 2 (with reasoning)"
    ],
    "risks": ["Anticipated risk 1", "Potential risk 2"],
    "opportunities": ["Discovered opportunity 1", "Potential opportunity 2"]
  }}
"""

        results = [run_panelist_turn(self.llm_service, p_config, prompt, trace_id) for p_config in panel_configs]

        turn_outputs, round_metrics, successful_panelists = _process_turn_results(review_id, review_room_id, 1, results, [])

        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "initial_turn_complete"}).model_dump_json())
        run_rebuttal_turn.delay(review_id, review_room_id, turn_outputs, [round_metrics], [p.model_dump() for p in successful_panelists], trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed to start review {review_id}: {e}")
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in initial turn for review {review_id}: {e}", exc_info=True)
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_rebuttal_turn(self: BaseTask, review_id: str, review_room_id: str, turn_1_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], successful_panelists: List[Dict[str, Any]], trace_id: str):
    try:
        panel_configs = [ProviderPanelistConfig(**p) for p in successful_panelists]
        round_1_summaries = []
        for persona, output in turn_1_outputs.items():
            arguments_str = "\n- ".join(output.get('arguments', []))
            risks_str = "\n- ".join(output.get('risks', []))
            opportunities_str = "\n- ".join(output.get('opportunities', []))
            
            summary = f"""Panelist: {persona}
Key Takeaway: {output.get('key_takeaway', 'N/A')}
Arguments:
- {arguments_str}
Risks:
- {risks_str}
Opportunities:
- {opportunities_str}"""
            round_1_summaries.append(summary)

        rebuttal_context = "\n\n---\n\n".join(round_1_summaries)

        prompt = f"""Rebuttal Round.
Here are the summaries of the initial arguments:
{rebuttal_context}

Review these arguments carefully.
- If there are differences, analyze them and clarify or improve weak points.
- If they are mostly aligned, reinforce the shared perspective by pointing out missing factors, hidden risks, or practical details.
- **When you state a disagreement or make an addition, you must provide a brief reasoning for it.**
- Only state "the arguments are sufficient" if you believe no meaningful improvement is possible (this should be rare).
- Your output must be in the specified JSON format.
- The JSON schema you must adhere to is:
  {{
    "round": 2,
    "agreements": [
      "Summary of a round 1 argument you fully agree with"
    ],
    "disagreements": [
      {{
        "point": "The argument you want to challenge or refine",
        "reasoning": "The logical flaw or why it's not realistic"
      }}
    ],
    "additions": [
      {{
        "point": "A new consideration missed in round 1",
        "reasoning": "Why this is important"
      }}
    ]
  }}
"""
        
        results = [run_panelist_turn(self.llm_service, p_config, prompt, f"{trace_id}-r2") for p_config in panel_configs]
        turn_outputs, round_metrics, successful_panelists = _process_turn_results(review_id, review_room_id, 2, results, all_metrics)
        
        all_metrics.append(round_metrics)
        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "rebuttal_turn_complete"}).model_dump_json())
        run_synthesis_turn.delay(review_id, review_room_id, turn_1_outputs, turn_outputs, all_metrics, [p.model_dump() for p in successful_panelists], trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed rebuttal turn for review {review_id}: {e}")
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in rebuttal turn for review {review_id}: {e}", exc_info=True)
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_synthesis_turn(self: BaseTask, review_id: str, review_room_id: str, turn_1_outputs: Dict[str, Any], turn_2_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], successful_panelists: List[Dict[str, Any]], trace_id: str):
    try:
        panel_configs = [ProviderPanelistConfig(**p) for p in successful_panelists]
        r1_context = "\n".join([f"Key takeaway from {p}: {o.get('key_takeaway', 'N/A')}" for p, o in turn_1_outputs.items()])

        r2_context_parts = []
        for persona, output in turn_2_outputs.items():
            agreements = "\n".join(f"- {a}" for a in output.get("agreements", []))
            disagreements = "\n".join(f"- Point: {d['point']}, Reasoning: {d['reasoning']}" for d in output.get("disagreements", []))
            additions = "\n".join(f"- Point: {a['point']}, Reasoning: {a['reasoning']}" for a in output.get("additions", []))
            r2_context_parts.append(f"""Panelist: {persona}
Agreements:
{agreements}
Disagreements:
{disagreements}
Additions:
{additions}""")
        r2_context = "\n\n---\n\n".join(r2_context_parts)

        synthesis_context = f"Initial Arguments:\n{r1_context}\n\nRebuttal Arguments:\n{r2_context}"
        prompt = f"""Synthesis Round.
Based on all previous arguments from round 1 and 2, please synthesize them into your final, comprehensive position.
Provide actionable recommendations based on your conclusion.

{synthesis_context}

Your output must be in the specified JSON format.
- The JSON schema you must adhere to is:
  {{
    "round": 3,
    "executive_summary": "A high-level summary of my final position, synthesizing all discussions.",
    "conclusion": "The detailed, comprehensive conclusion supporting the summary.",
    "recommendations": [
      "Specific, actionable recommendation 1, based on the conclusion.",
      "Specific, actionable recommendation 2, based on the conclusion."
    ]
  }}
"""

        results = [run_panelist_turn(self.llm_service, p_config, prompt, f"{trace_id}-r3") for p_config in panel_configs]
        turn_outputs, round_metrics, successful_panelists = _process_turn_results(review_id, review_room_id, 3, results, all_metrics)
        
        all_metrics.append(round_metrics)
        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "synthesis_turn_complete"}).model_dump_json())
        generate_consolidated_report.delay(review_id, turn_outputs, all_metrics, trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed synthesis turn for review {review_id}: {e}")
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in synthesis turn for review {review_id}: {e}", exc_info=True)
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def generate_consolidated_report(self: BaseTask, review_id: str, turn_3_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], trace_id: str):
    try:
        system_prompt = "You are the Chief Editor. Your task is to synthesize final reports from multiple AI panelists into a single, cohesive, and actionable final report for a key decision-maker. Pay close attention to points of consensus and disagreement."

        user_prompt = f"""The following are the final reports from the AI panelists:
{json.dumps(list(turn_3_outputs.values()), indent=2)}

Please create a consolidated final report.
- In the executive summary, clearly state the strongest points of consensus and any significant remaining disagreements among the panelists.
- Your output must be in the specified JSON format.
- The JSON schema you must adhere to is:
  {{
    "executive_summary": "The final summary, including key insights from the entire discussion.",
    "strongest_consensus": [
      "Key point 1 that panelists commonly agreed on.",
      "Key point 2 that panelists commonly agreed on."
    ],
    "remaining_disagreements": [
      "Significant disagreement 1, if any."
    ],
    "recommendations": [
      "Consolidated final recommendation 1 (highest priority).",
      "Consolidated final recommendation 2."
    ]
  }}
"""
        # Use a powerful model for the final synthesis
        final_report_str, _ = self.llm_service.invoke_sync(
            provider_name="openai",
            model="gpt-4-turbo",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=f"{trace_id}-report",
            response_format="json"
        )

        final_report_data = json.loads(final_report_str)
        storage_service.save_final_report(review_id=review_id, report_data=final_report_data)

        if settings.METRICS_ENABLED:
            total_tokens = sum(m.get("total_tokens", 0) for r in all_metrics for m in r if m)
            if settings.DAILY_ORG_TOKEN_BUDGET:
                redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                today_key = f"daily_token_usage:{datetime.utcnow().strftime('%Y-%m-%d')}"
                redis_client.incrby(today_key, total_tokens)
                redis_client.expire(today_key, 60 * 60 * 25)
                redis_client.close()

        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "completed"}).model_dump_json())
    except Exception as e:
        logger.error(f"Error generating consolidated report for review {review_id}: {e}", exc_info=True)
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "Failed to generate final report."}})
        raise
