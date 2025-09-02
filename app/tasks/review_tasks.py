import logging
import time
import json
import asyncio
import redis
from datetime import datetime
from typing import List, Dict, Any, Callable, Awaitable, Tuple, Union, Optional
from asgiref.sync import async_to_sync
from celery import Task, states
from celery.exceptions import Ignore
from tenacity import retry, stop_after_attempt, wait_exponential
from collections import defaultdict

from app.celery_app import celery_app
from app.config.settings import settings
from app.services.llm_service import LLMService
from app.services.storage_service import StorageService
from app.models.schemas import Message, ReviewMetrics, WebSocketMessage
from app.services.redis_pubsub import redis_pubsub_manager
from app.services.llm_strategy import llm_strategy_service, PanelistConfig
from app.core.metrics import LLM_CALLS_TOTAL, LLM_LATENCY_SECONDS, LLM_TOKENS_TOTAL
from app.utils.helpers import generate_id, get_current_timestamp

logger = logging.getLogger(__name__)

class BudgetExceededError(Exception):
    """Custom exception for when a budget is exceeded."""
    pass

async def call_llm_with_metrics(llm_func: Callable[..., Awaitable[Tuple[str, Dict[str, Any]]]], topic: str, round_number: int, mode: str, panel_reports: List[Dict[str, Any]] = None, request_id: str = "", provider_name: str = "openai", **kwargs) -> Tuple[str, Dict[str, Any]]:
    """Call LLM function and collect metrics"""
    start_time = time.time()
    
    try:
        if panel_reports:
            result, metrics = await llm_func(panel_reports=panel_reports, **kwargs)
        else:
            result, metrics = await llm_func(topic=topic, instruction=kwargs.get('instruction', ''), **kwargs)
        
        # Record metrics
        duration = time.time() - start_time
        LLM_CALLS_TOTAL.labels(provider=provider_name, mode=mode).inc()
        LLM_LATENCY_SECONDS.labels(provider=provider_name, mode=mode).observe(duration)
        
        if metrics and 'total_tokens' in metrics:
            LLM_TOKENS_TOTAL.labels(provider=provider_name, mode=mode).inc(metrics['total_tokens'])
        
        return result, metrics
    except Exception as e:
        duration = time.time() - start_time
        LLM_CALLS_TOTAL.labels(provider=provider_name, mode="error").inc()
        LLM_LATENCY_SECONDS.labels(provider=provider_name, mode="error").observe(duration)
        raise

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def invoke_llm_with_retry(llm_service: LLMService, provider_name: str, topic: str, instruction: str, request_id: str) -> Tuple[str, Dict[str, Any]]:
    """Invoke LLM with retry logic"""
    provider = llm_service.get_provider(provider_name)
    return await provider.invoke(topic=topic, instruction=instruction, request_id=request_id)

async def run_panelist_turn_with_fallback(llm_service: LLMService, panelist_config: PanelistConfig, topic: str, instruction: str, request_id: str) -> Tuple[PanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]:
    """Run a single panelist turn with fallback handling"""
    try:
        result = await invoke_llm_with_retry(llm_service, panelist_config.provider, topic, instruction, f"{request_id}-{panelist_config.provider}")
        return panelist_config, result
    except Exception as e:
        logger.error(f"Failed to get response from {panelist_config.provider}: {e}")
        return panelist_config, e

async def _save_panelist_message(storage_service: StorageService, review_room_id: str, content: str, persona: str, round_num: int):
    """Saves a panelist's output as a message in the review room."""
    message = Message(
        message_id=generate_id("msg"),
        room_id=review_room_id,
        role="assistant",
        content=content,
        user_id="assistant",  # System user for AI messages
        timestamp=get_current_timestamp(),
        metadata={"persona": persona, "round": round_num}
    )
    await storage_service.save_message(message)

def _check_review_budget(review_id: str, all_metrics: List[List[Dict[str, Any]]]):
    """Checks if the review has exceeded its token budget."""
    if not settings.PER_REVIEW_TOKEN_BUDGET:
        return

    total_tokens = sum(m.get("total_tokens", 0) for r_metrics in all_metrics for m in r_metrics)
    if total_tokens > settings.PER_REVIEW_TOKEN_BUDGET:
        error_msg = f"Review {review_id} exceeded token budget of {settings.PER_REVIEW_TOKEN_BUDGET} with {total_tokens} tokens."
        logger.error(error_msg)
        raise BudgetExceededError(error_msg)

async def _process_turn_results(
    review_id: str,
    review_room_id: str,
    round_num: int,
    results: List[Tuple[PanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]],
    storage_service: StorageService,
    all_previous_metrics: List[List[Dict[str, Any]]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[PanelistConfig]]:
    """
    Processes results from a single turn, saves messages, and collects metrics.
    """
    turn_outputs, round_metrics, successful_panelists = {}, [], []

    for panelist_config, result in results:
        persona = panelist_config.persona
        if isinstance(result, BaseException):
            logger.error(f"Panelist {persona} failed in round {round_num}: {result}")
            round_metrics.append({"persona": persona, "success": False, "error": str(result), "provider": panelist_config.provider})
        else:
            content, metrics = result
            turn_outputs[persona] = json.loads(content)
            round_metrics.append(metrics)
            successful_panelists.append(panelist_config)
            await _save_panelist_message(storage_service, review_room_id, content, persona, round_num)

    # Combine metrics and check budget
    _check_review_budget(review_id, all_previous_metrics + [round_metrics])

    return turn_outputs, round_metrics, successful_panelists

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_initial_panel_turn(self: Task, review_id: str, review_room_id: str, topic: str, instruction: str, panelists_override: Optional[List[str]], trace_id: str):
    from app.core.secrets import env_secrets_provider
    storage_service = StorageService(env_secrets_provider)
    try:
        if settings.DAILY_ORG_TOKEN_BUDGET:
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            today_key = f"daily_token_usage:{datetime.utcnow().strftime('%Y-%m-%d')}"
            current_usage = int(redis_client.get(today_key) or 0)
            if current_usage > settings.DAILY_ORG_TOKEN_BUDGET:
                raise BudgetExceededError(f"Daily token budget of {settings.DAILY_ORG_TOKEN_BUDGET} exceeded.")

        llm_service = LLMService(env_secrets_provider)
        panel_configs = llm_strategy_service.get_default_panelists()
        if panelists_override:
            panel_configs = [p for p in panel_configs if p.provider in panelists_override]

        tasks = [run_panelist_turn_with_fallback(llm_service, p_config, topic, instruction, trace_id) for p_config in panel_configs]
        results = async_to_sync(asyncio.gather)(*tasks)
        turn_outputs, round_metrics, successful_panelists = async_to_sync(_process_turn_results)(review_id, review_room_id, 1, results, storage_service, [])

        async_to_sync(redis_pubsub_manager.publish)(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "initial_turn_complete"}).model_dump_json())
        run_rebuttal_turn.delay(review_id, review_room_id, turn_outputs, [round_metrics], [p.model_dump() for p in successful_panelists], trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed to start review {review_id}: {e}")
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in initial turn for review {review_id}: {e}", exc_info=True)
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_rebuttal_turn(self: Task, review_id: str, review_room_id: str, turn_1_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], successful_panelists: List[Dict[str, Any]], trace_id: str):
    """Second turn: panelists respond to each other's initial arguments"""
    from app.core.secrets import env_secrets_provider
    storage_service = StorageService(env_secrets_provider)
    try:
        llm_service = LLMService(env_secrets_provider)
        panel_configs = [PanelistConfig(**p) for p in successful_panelists]
        
        # Create rebuttal prompts based on turn 1 outputs
        rebuttal_context = "\n".join([f"{provider}: {output.get('summary', '')}" for provider, output in turn_1_outputs.items()])
        
        tasks = [run_panelist_turn_with_fallback(llm_service, p_config, f"Rebuttal Round - Previous arguments:\n{rebuttal_context}", "Provide a thoughtful rebuttal or counter-argument to the previous responses.", f"{trace_id}-r2") for p_config in panel_configs]
        results = async_to_sync(asyncio.gather)(*tasks)
        turn_outputs, round_metrics, successful_panelists = async_to_sync(_process_turn_results)(review_id, review_room_id, 2, results, storage_service, all_metrics)
        
        all_metrics.append(round_metrics)
        async_to_sync(redis_pubsub_manager.publish)(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "rebuttal_turn_complete"}).model_dump_json())
        run_synthesis_turn.delay(review_id, review_room_id, turn_1_outputs, turn_outputs, all_metrics, [p.model_dump() for p in successful_panelists], trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed rebuttal turn for review {review_id}: {e}")
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in rebuttal turn for review {review_id}: {e}", exc_info=True)
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_synthesis_turn(self: Task, review_id: str, review_room_id: str, turn_1_outputs: Dict[str, Any], turn_2_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], successful_panelists: List[Dict[str, Any]], trace_id: str):
    """Third turn: panelists synthesize all previous arguments into final positions"""
    from app.core.secrets import env_secrets_provider
    storage_service = StorageService(env_secrets_provider)
    try:
        llm_service = LLMService(env_secrets_provider)
        panel_configs = [PanelistConfig(**p) for p in successful_panelists]
        
        # Create synthesis context from both previous turns
        synthesis_context = "Initial Arguments:\n" + "\n".join([f"{provider}: {output.get('summary', '')}" for provider, output in turn_1_outputs.items()])
        synthesis_context += "\n\nRebuttal Arguments:\n" + "\n".join([f"{provider}: {output.get('summary', '')}" for provider, output in turn_2_outputs.items()])
        
        tasks = [run_panelist_turn_with_fallback(llm_service, p_config, f"Synthesis Round - All previous arguments:\n{synthesis_context}", "Synthesize all arguments into your final position and recommendations.", f"{trace_id}-r3") for p_config in panel_configs]
        results = async_to_sync(asyncio.gather)(*tasks)
        turn_outputs, round_metrics, successful_panelists = async_to_sync(_process_turn_results)(review_id, review_room_id, 3, results, storage_service, all_metrics)
        
        all_metrics.append(round_metrics)
        async_to_sync(redis_pubsub_manager.publish)(f"review_{review_id}", WebSocketMessage(type="status_update", review_id=review_id, payload={"status": "synthesis_turn_complete"}).model_dump_json())
        generate_consolidated_report.delay(review_id, turn_outputs, all_metrics, trace_id)
    except BudgetExceededError as e:
        logger.error(f"Failed synthesis turn for review {review_id}: {e}")
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in synthesis turn for review {review_id}: {e}", exc_info=True)
        async_to_sync(storage_service.update_review)(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def generate_consolidated_report(self: Task, review_id: str, turn_3_outputs: Dict[str, Any], all_metrics: List[List[Dict[str, Any]]], trace_id: str):
    from app.core.secrets import env_secrets_provider
    llm_service, storage_service = LLMService(env_secrets_provider), StorageService(env_secrets_provider)

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
