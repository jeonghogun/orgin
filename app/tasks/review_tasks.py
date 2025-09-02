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
from app.services.llm_strategy import llm_strategy_service, PanelistConfig
from app.utils.helpers import generate_id, get_current_timestamp
from app.tasks.base_task import BaseTask
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

class BudgetExceededError(Exception):
    """Custom exception for when a budget is exceeded."""
    pass

def run_panelist_turn(
    llm_service: LLMService,
    panelist_config: PanelistConfig,
    prompt: str,
    request_id: str
) -> Tuple[PanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]:
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

def _save_panelist_message(task_self: BaseTask, review_room_id: str, content: str, persona: str, round_num: int):
    """Saves a panelist's output as a message in the review room."""
    message = Message(
        message_id=generate_id("msg"),
        room_id=review_room_id,
        role="assistant",
        content=content,
        user_id="assistant",
        timestamp=get_current_timestamp(),
        metadata={"persona": persona, "round": round_num}
    )
    task_self.storage_service.save_message(message)

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
    task_self: BaseTask,
    review_id: str,
    review_room_id: str,
    round_num: int,
    results: List[Tuple[PanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]],
    all_previous_metrics: List[List[Dict[str, Any]]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[PanelistConfig]]:
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
                _save_panelist_message(task_self, review_room_id, content, persona, round_num)
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

        prompt = f"Topic: {topic}\nInstruction: {instruction}"

        results = [run_panelist_turn(self.llm_service, p_config, prompt, trace_id) for p_config in panel_configs]

        turn_outputs, round_metrics, successful_panelists = _process_turn_results(self, review_id, review_room_id, 1, results, [])

        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "initial_turn_complete"}).model_dump_json())
        run_rebuttal_turn.delay(review_id, review_room_id, turn_outputs, [round_metrics], [p.model_dump() for p in successful_panelists], trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed to start review {review_id}: {e}")
        self.storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in initial turn for review {review_id}: {e}", exc_info=True)
        self.storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_rebuttal_turn(self: BaseTask, review_id: str, review_room_id: str, turn_1_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], successful_panelists: List[Dict[str, Any]], trace_id: str):
    try:
        panel_configs = [PanelistConfig(**p) for p in successful_panelists]
        rebuttal_context = "\n".join([f"Summary from {persona}: {output.get('summary', '')}" for persona, output in turn_1_outputs.items()])
        prompt = f"Rebuttal Round. Here are the summaries of the initial arguments:\n{rebuttal_context}\n\nPlease provide a thoughtful rebuttal or build upon the other arguments."
        
        results = [run_panelist_turn(self.llm_service, p_config, prompt, f"{trace_id}-r2") for p_config in panel_configs]
        turn_outputs, round_metrics, successful_panelists = _process_turn_results(self, review_id, review_room_id, 2, results, all_metrics)
        
        all_metrics.append(round_metrics)
        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "rebuttal_turn_complete"}).model_dump_json())
        run_synthesis_turn.delay(review_id, review_room_id, turn_1_outputs, turn_outputs, all_metrics, [p.model_dump() for p in successful_panelists], trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed rebuttal turn for review {review_id}: {e}")
        self.storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in rebuttal turn for review {review_id}: {e}", exc_info=True)
        self.storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_synthesis_turn(self: BaseTask, review_id: str, review_room_id: str, turn_1_outputs: Dict[str, Any], turn_2_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], successful_panelists: List[Dict[str, Any]], trace_id: str):
    try:
        panel_configs = [PanelistConfig(**p) for p in successful_panelists]
        synthesis_context = "Initial Arguments:\n" + "\n".join([f"Summary from {p}: {o.get('summary', '')}" for p, o in turn_1_outputs.items()])
        synthesis_context += "\n\nRebuttal Arguments:\n" + "\n".join([f"Summary from {p}: {o.get('summary', '')}" for p, o in turn_2_outputs.items()])
        prompt = f"Synthesis Round. Based on all previous arguments, please synthesize them into your final, comprehensive position and provide actionable recommendations.\n\n{synthesis_context}"

        results = [run_panelist_turn(self.llm_service, p_config, prompt, f"{trace_id}-r3") for p_config in panel_configs]
        turn_outputs, round_metrics, successful_panelists = _process_turn_results(self, review_id, review_room_id, 3, results, all_metrics)
        
        all_metrics.append(round_metrics)
        redis_pubsub_manager.publish_sync(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "synthesis_turn_complete"}).model_dump_json())
        generate_consolidated_report.delay(review_id, turn_outputs, all_metrics, trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed synthesis turn for review {review_id}: {e}")
        self.storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in synthesis turn for review {review_id}: {e}", exc_info=True)
        self.storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def generate_consolidated_report(self: BaseTask, review_id: str, turn_3_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], trace_id: str):
    try:
        synthesis_prompt = "The following are the final reports from several AI panelists. Please synthesize them into a single, consolidated final report. The final report should include an executive summary and a list of actionable recommendations. Respond with only the JSON for the final report. The JSON schema should be: {'executive_summary': '...', 'recommendations': ['...', '...']}\n\n"
        synthesis_prompt += json.dumps(list(turn_3_outputs.values()), indent=2)

        final_report_str, _ = self.llm_service.invoke_sync(
            provider_name="openai",
            model="gpt-4-turbo",
            system_prompt="You are a final report synthesis expert.",
            user_prompt=synthesis_prompt,
            request_id=f"{trace_id}-report",
            response_format="json"
        )

        final_report_data = json.loads(final_report_str)
        self.storage_service.save_final_report(review_id=review_id, report_data=final_report_data)

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
        self.storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "Failed to generate final report."}})
        raise
