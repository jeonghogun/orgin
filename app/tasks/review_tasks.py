import logging
import time
import json
import asyncio
import redis
from datetime import datetime
from typing import List, Dict, Any, Callable, Awaitable, Tuple, Union
from asgiref.sync import async_to_sync
from celery import Task, states
from celery.exceptions import Ignore
from tenacity import retry, stop_after_attempt, wait_exponential
from collections import defaultdict

from app.celery_app import celery_app
from app.config.settings import settings
from app.services.llm_service import LLMService
from app.services.storage_service import StorageService
from app.models.schemas import ReviewMetrics, WebSocketMessage
from app.services.redis_pubsub import redis_pubsub_manager
from app.services.llm_strategy import llm_strategy_service, PanelistConfig
from app.core.metrics import LLM_CALLS_TOTAL, LLM_LATENCY_SECONDS, LLM_TOKENS_TOTAL

logger = logging.getLogger(__name__)

class BudgetExceededError(Exception):
    """Custom exception for when a budget is exceeded."""
    pass

# ... (call_llm_with_metrics, invoke_llm_with_retry, run_panelist_turn_with_fallback are unchanged)

async def _process_turn_results(review_id: str, round_num: int, results: List[Tuple[PanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]], storage_service: StorageService, all_previous_metrics: List[List[Dict[str, Any]]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[PanelistConfig]]:
    turn_outputs, round_metrics, successful_panelists = {}, [], []
    for panelist_config, result in results:
        persona = panelist_config.persona
        if isinstance(result, BaseException):
            logger.error(f"Final error for persona {persona} in round {round_num}: {result}")
            round_metrics.append({"persona": persona, "success": False, "error": str(result), "provider": panelist_config.provider})
        else:
            content, metrics = result
            turn_outputs[persona] = json.loads(content)
            round_metrics.append(metrics)
            successful_panelists.append(panelist_config)
            await storage_service.log_review_event({"review_id": review_id, "ts": time.time(), "type": "panel_output", "round": round_num, "actor": persona, "content": content})

    # Check per-review budget
    if settings.PER_REVIEW_TOKEN_BUDGET:
        current_total_tokens = sum(m.get("total_tokens", 0) for r in all_previous_metrics for m in r)
        current_total_tokens += sum(m.get("total_tokens", 0) for m in round_metrics)
        if current_total_tokens > settings.PER_REVIEW_TOKEN_BUDGET:
            raise BudgetExceededError(f"Review {review_id} exceeded token budget of {settings.PER_REVIEW_TOKEN_BUDGET} with {current_total_tokens} tokens.")

    return turn_outputs, round_metrics, successful_panelists

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_initial_panel_turn(self: Task, review_id: str, topic: str, instruction: str, panelists_override: Optional[List[str]], trace_id: str):
    storage_service = StorageService()
    try:
        if settings.DAILY_ORG_TOKEN_BUDGET:
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            today_key = f"daily_token_usage:{datetime.utcnow().strftime('%Y-%m-%d')}"
            current_usage = int(redis_client.get(today_key) or 0)
            if current_usage > settings.DAILY_ORG_TOKEN_BUDGET:
                raise BudgetExceededError(f"Daily token budget of {settings.DAILY_ORG_TOKEN_BUDGET} exceeded.")

        llm_service = LLMService()
        panel_configs = llm_strategy_service.get_default_panelists()
        if panelists_override:
            panel_configs = [p for p in panel_configs if p.provider in panelists_override]

        tasks = [run_panelist_turn_with_fallback(llm_service, p_config, topic, instruction, trace_id) for p_config in panel_configs]
        results = async_to_sync(asyncio.gather)(*tasks)
        turn_outputs, round_metrics, successful_panelists = async_to_sync(_process_turn_results)(review_id, 1, results, storage_service, [])

        async_to_sync(redis_pubsub_manager.publish)(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "initial_turn_complete"}).model_dump_json())
        run_rebuttal_turn.delay(review_id, turn_outputs, [round_metrics], [p.model_dump() for p in successful_panelists], trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed to start review {review_id}: {e}")
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in initial turn for review {review_id}: {e}", exc_info=True)
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

# ... other tasks would need similar try/except blocks for BudgetExceededError ...

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def generate_consolidated_report(self: Task, review_id: str, turn_3_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], trace_id: str):
    llm_service, storage_service = LLMService(), StorageService()

    async def _report_and_metrics_logic():
        report_content, _ = await call_llm_with_metrics(llm_service.generate_consolidated_report, topic="", round_number=3, mode="synthesis", panel_reports=list(turn_3_outputs.values()), request_id=f"{trace_id}-report", provider_name="openai")
        final_report_data = json.loads(report_content)
        await storage_service.save_final_report(review_id=review_id, report_data=final_report_data)

        if settings.METRICS_ENABLED:
            total_tokens = sum(m.get("total_tokens", 0) for r in all_metrics for m in r)
            if settings.DAILY_ORG_TOKEN_BUDGET:
                redis_client = redis.from_url(settings.REDIS_URL)
                today_key = f"daily_token_usage:{datetime.utcnow().strftime('%Y-%m-%d')}"
                redis_client.incrby(today_key, total_tokens)
                redis_client.expire(today_key, 60 * 60 * 25)

            # ... rest of metrics saving logic

    async_to_sync(_report_and_metrics_logic)()
    async_to_sync(redis_pubsub_manager.publish)(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "completed"}).model_dump_json())
