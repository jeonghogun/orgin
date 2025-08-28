import logging
import time
import json
import asyncio
from typing import List, Dict, Any, Callable, Awaitable, Tuple, Union
from asgiref.sync import async_to_sync
from celery import Task
from app.celery_app import celery_app
from app.config.settings import settings
from app.services.llm_service import LLMService
from app.services.storage_service import StorageService
from app.models.schemas import ReviewMetrics, WebSocketMessage
from app.services.redis_pubsub import redis_pubsub_manager

logger = logging.getLogger(__name__)

# Map providers to the personas they will represent in the debate.
# This makes the multi-agent system concrete.
PROVIDER_PERSONA_MAP = {
    "openai": "AGI 비관론자",
    "gemini": "AGI 낙관론자",
    "claude": "AGI 중립론자",
}
latest_alerts: List[Dict[str, Any]] = []


async def call_llm_with_metrics(
    llm_function: Callable[..., Awaitable[Tuple[Any, Dict[str, Any]]]], **kwargs: Any
) -> Tuple[Any, Dict[str, Any]]:
    start_time = time.time()
    content, metrics = await llm_function(**kwargs)
    end_time = time.time()
    duration = end_time - start_time

    metrics["duration_seconds"] = duration
    metrics["success"] = True

    return content, metrics


async def run_panelist_turn_with_fallback(
    llm_service: LLMService, provider_name: str, persona: str, topic: str, instruction: str, request_id: str
) -> Tuple[str, Union[Tuple[Any, Dict[str, Any]], BaseException]]:
    """Helper to run a single panelist's turn with fallback to a default provider."""
    try:
        # First attempt with the designated provider
        llm_provider = llm_service.get_provider(provider_name)
        content, metrics = await call_llm_with_metrics(
            llm_provider.invoke,
            model=settings.LLM_MODEL,
            system_prompt=f"You are {persona}, an AI expert.",
            user_prompt=f"Topic: {topic}\nInstruction: {instruction}",
            request_id=f"{request_id}-{provider_name}",
        )
        metrics.update({"persona": persona, "provider": provider_name, "fallback_used": False})
        return persona, (content, metrics)
    except Exception as e:
        logger.warning(f"Initial attempt failed for provider {provider_name} with persona {persona}. Error: {e}. Attempting fallback.")

        # Fallback to the default provider (OpenAI)
        try:
            fallback_provider_name = "openai"
            llm_provider = llm_service.get_provider(fallback_provider_name)
            content, metrics = await call_llm_with_metrics(
                llm_provider.invoke,
                model=settings.LLM_MODEL,
                system_prompt=f"You are {persona}, an AI expert.",
                user_prompt=f"Topic: {topic}\nInstruction: {instruction}",
                request_id=f"{request_id}-{provider_name}-fallback",
            )
            metrics.update({"persona": persona, "provider": provider_name, "fallback_used": True, "original_error": str(e)})
            return persona, (content, metrics)
        except Exception as fallback_e:
            logger.error(f"Fallback attempt also failed for persona {persona}. Error: {fallback_e}")
            return persona, fallback_e


async def _process_initial_turn_results(
    review_id: str,
    results: List[Tuple[str, Union[Tuple[Any, Dict[str, Any]], BaseException]]],
    storage_service: StorageService,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Processes the results from the initial panel turn, logging events and handling errors."""
    turn_1_outputs: Dict[str, Any] = {}
    round_1_metrics: List[Dict[str, Any]] = []

    for persona, result in results:
        if isinstance(result, BaseException):
            logger.error(f"Final error for persona {persona} after fallback attempt: {result}")
            turn_1_outputs[persona] = {"error": str(result)}
            round_1_metrics.append({"persona": persona, "success": False, "error": str(result)})
        else:
            content, metrics = result
            turn_1_outputs[persona] = json.loads(content)
            round_1_metrics.append(metrics)
            await storage_service.log_review_event(
                {
                    "review_id": review_id,
                    "ts": time.time(),
                    "type": "panel_output",
                    "round": 1,
                    "actor": persona,
                    "content": content,
                }
            )
    return turn_1_outputs, round_1_metrics


async def initial_turn_logic(
    review_id: str,
    topic: str,
    instruction: str,
    trace_id: str,
    panelists: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm_service = LLMService()
    storage_service = StorageService()
    tasks: List[Awaitable[Tuple[str, Union[Tuple[Any, Dict[str, Any]], BaseException]]]] = []

    # If panelists are provided via API, use them. Otherwise, use the default map.
    panel_map = {p: PROVIDER_PERSONA_MAP.get(p, f"Persona for {p}") for p in panelists} if panelists else PROVIDER_PERSONA_MAP

    # If the global toggle is on, force all panelists to use the default provider
    if settings.FORCE_DEFAULT_PROVIDER:
        default_provider_name = "openai"
        panel_map = {f"{default_provider_name}-{i}": persona for i, persona in enumerate(panel_map.values())}

    for provider_key, persona in panel_map.items():
        provider_name = provider_key.split("-")[0]
        tasks.append(
            run_panelist_turn_with_fallback(
                llm_service, provider_name, persona, topic, instruction, request_id=trace_id
            )
        )

    results = await asyncio.gather(*tasks)

    turn_1_outputs, round_1_metrics = await _process_initial_turn_results(
        review_id, results, storage_service
    )

    return turn_1_outputs, round_1_metrics


@celery_app.task(bind=True)
def run_initial_panel_turn(
    self,
    review_id: str,
    topic: str,
    instruction: str,
    panelists: Optional[List[str]],
    trace_id: str,
):
    logger.info(
        f"Starting initial panel turn for review: {review_id} with trace_id: {trace_id}"
    )
    turn_outputs, round_metrics = async_to_sync(initial_turn_logic)(
        review_id, topic, instruction, trace_id, panelists
    )
    msg = WebSocketMessage(
        type="status_update",
        review_id=review_id,
        payload={"status": "initial_turn_complete"},
    )
    async_to_sync(redis_pubsub_manager.publish)(
        f"review_{review_id}", msg.model_dump_json()
    )

    # Pass the dynamically determined panelists (and their outputs) to the next turn
    participating_personas = list(turn_outputs.keys())
    run_rebuttal_turn.delay(
        review_id, turn_outputs, round_metrics, participating_personas, trace_id=trace_id
    )


async def _prepare_rebuttal_prompt(
    llm_service, turn_1_outputs, current_persona, trace_id
):
    """Prepares the system and user prompts for the rebuttal turn."""
    own_previous_output = turn_1_outputs.get(current_persona, {})

    peer_summaries: List[str] = []
    for peer_persona, peer_output in turn_1_outputs.items():
        if peer_persona != current_persona:
            summary, _ = await call_llm_with_metrics(
                llm_service.summarize_for_debate,
                panelist_output=json.dumps(peer_output),
                request_id=f"{trace_id}-summary-{peer_persona}",
            )
            peer_summaries.append(f"--- {peer_persona}'s Summary ---\n{summary}\n")

    system_prompt = f"""You are {current_persona}, continuing a debate. You are in Turn 2 (Rebuttal). Your goal is to respond to your peers' arguments from Turn 1. Maintain your persona and be consistent with your previous arguments."""
    user_prompt = f"""Your previous output (full text):\n{json.dumps(own_previous_output)}\n\nSummaries of your peers' outputs:\n{''.join(peer_summaries)}\n\nPlease provide your rebuttal and analysis."""

    return system_prompt, user_prompt


async def rebuttal_turn_logic(
    review_id: str,
    turn_1_outputs: Dict[str, Any],
    trace_id: str,
    panelists: List[str],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm_service = LLMService()
    storage_service = StorageService()
    turn_2_outputs: Dict[str, Any] = {}
    round_2_metrics: List[Dict[str, Any]] = []

    tasks: List[Awaitable[Tuple[Any, Dict[str, Any]]]] = []
    for current_persona in panelists:
        system_prompt, user_prompt = await _prepare_rebuttal_prompt(
            llm_service, turn_1_outputs, current_persona, trace_id
        )
        logger.debug(
            f"Rebuttal prompt for {current_persona} (first 500 chars): {user_prompt[:500]}"
        )

        tasks.append(
            call_llm_with_metrics(
                llm_service.generate_panel_analysis,
                topic="",  # Topic is not needed for rebuttal
                persona=current_persona,
                instruction=user_prompt,  # Pass the full context as instruction
                request_id=f"{trace_id}-{current_persona}",
            )
        )

    results: List[Union[Tuple[Any, Dict[str, Any]], BaseException]] = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        current_persona = panelists[i]
        if isinstance(result, BaseException):
            logger.error(f"Error generating rebuttal for {current_persona}: {result}")
            turn_2_outputs[current_persona] = {"error": str(result)}
            round_2_metrics.append(
                {"persona": current_persona, "success": False, "error": str(result)}
            )
        else:
            content, metrics = result
            turn_2_outputs[current_persona] = json.loads(content)
            metrics["persona"] = current_persona
            round_2_metrics.append(metrics)
            await storage_service.log_review_event(
                {
                    "review_id": review_id,
                    "ts": time.time(),
                    "type": "panel_output",
                    "round": 2,
                    "actor": current_persona,
                    "content": content,
                }
            )

    return turn_2_outputs, round_2_metrics


@celery_app.task(bind=True)
def run_rebuttal_turn(
    self: Task,
    review_id: str,
    turn_1_outputs: Dict[str, Any],
    round_1_metrics: List[Dict[str, Any]],
    panelists: List[str],
    trace_id: str,
) -> None:
    logger.info(f"Starting rebuttal turn for review: {review_id} with trace_id: {trace_id}")
    turn_2_outputs, round_2_metrics = async_to_sync(rebuttal_turn_logic)(
        review_id, turn_1_outputs, trace_id, panelists
    )
    all_metrics: List[List[Dict[str, Any]]] = [round_1_metrics, round_2_metrics]
    msg = WebSocketMessage(
        type="status_update",
        review_id=review_id,
        payload={"status": "rebuttal_turn_complete"},
    )
    async_to_sync(redis_pubsub_manager.publish)(
        f"review_{review_id}", msg.model_dump_json()
    )

    participating_personas = list(turn_2_outputs.keys())
    run_synthesis_turn.delay(
        review_id,
        turn_1_outputs,
        turn_2_outputs,
        all_metrics,
        participating_personas,
        trace_id=trace_id,
    )


async def _prepare_synthesis_prompt(
    llm_service: LLMService,
    turn_1_outputs: Dict[str, Any],
    turn_2_outputs: Dict[str, Any],
    current_persona: str,
    trace_id: str,
) -> Tuple[str, str]:
    """Prepares the system and user prompts for the synthesis turn."""
    own_turn_1_output = turn_1_outputs.get(current_persona, {})
    own_turn_2_output = turn_2_outputs.get(current_persona, {})

    peer_summaries: List[str] = []
    for peer_persona, peer_output in turn_2_outputs.items():
        if peer_persona != current_persona:
            summary, _ = await call_llm_with_metrics(
                llm_service.summarize_for_debate,
                panelist_output=json.dumps(peer_output),
                request_id=f"{trace_id}-summary-{peer_persona}",
            )
            peer_summaries.append(f"--- {peer_persona}'s Turn 2 Summary ---\n{summary}\n")

    system_prompt = f"""You are {current_persona}, in the final turn of a debate (Turn 3: Synthesis). Your goal is to produce a final, synthesized opinion that considers your previous points and the rebuttals from your peers."""
    user_prompt = f"""Your Turn 1 Output:\n{json.dumps(own_turn_1_output)}\nYour Turn 2 Rebuttal:\n{json.dumps(own_turn_2_output)}\n\nSummaries of your peers' Turn 2 Rebuttals:\n{''.join(peer_summaries)}\n\nPlease provide your final, synthesized analysis."""
    return system_prompt, user_prompt


async def synthesis_turn_logic(
    review_id: str,
    turn_1_outputs: Dict[str, Any],
    turn_2_outputs: Dict[str, Any],
    trace_id: str,
    panelists: List[str],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm_service = LLMService()
    storage_service = StorageService()
    turn_3_outputs: Dict[str, Any] = {}
    round_3_metrics: List[Dict[str, Any]] = []

    tasks: List[Awaitable[Tuple[Any, Dict[str, Any]]]] = []
    for current_persona in panelists:
        system_prompt, user_prompt = await _prepare_synthesis_prompt(
            llm_service, turn_1_outputs, turn_2_outputs, current_persona, trace_id
        )
        logger.debug(f"Synthesis prompt for {current_persona} (first 500 chars): {user_prompt[:500]}")

        tasks.append(
            call_llm_with_metrics(
                llm_service.generate_panel_analysis,
                topic="",  # Topic is not needed for synthesis
                persona=current_persona,
                instruction=user_prompt,  # Pass the full context as instruction
                request_id=f"{trace_id}-{current_persona}",
            )
        )

    results: List[Union[Tuple[Any, Dict[str, Any]], BaseException]] = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        current_persona = panelists[i]
        if isinstance(result, BaseException):
            logger.error(f"Error generating synthesis for {current_persona}: {result}")
            turn_3_outputs[current_persona] = {"error": str(result)}
            round_3_metrics.append(
                {"persona": current_persona, "success": False, "error": str(result)}
            )
        else:
            content, metrics = result
            turn_3_outputs[current_persona] = json.loads(content)
            metrics["persona"] = current_persona
            round_3_metrics.append(metrics)
            await storage_service.log_review_event(
                {
                    "review_id": review_id,
                    "ts": time.time(),
                    "type": "panel_output",
                    "round": 3,
                    "actor": current_persona,
                    "content": content,
                }
            )

    return turn_3_outputs, round_3_metrics


@celery_app.task(bind=True)
def run_synthesis_turn(
    self: Task,
    review_id: str,
    turn_1_outputs: Dict[str, Any],
    turn_2_outputs: Dict[str, Any],
    all_metrics: List[List[Dict[str, Any]]],
    panelists: List[str],
    trace_id: str,
) -> None:
    logger.info(f"Starting synthesis turn for review: {review_id} with trace_id: {trace_id}")
    turn_3_outputs, round_3_metrics = async_to_sync(synthesis_turn_logic)(
        review_id, turn_1_outputs, turn_2_outputs, trace_id, panelists
    )
    all_metrics.append(round_3_metrics)
    msg = WebSocketMessage(
        type="status_update",
        review_id=review_id,
        payload={"status": "synthesis_turn_complete"},
    )
    async_to_sync(redis_pubsub_manager.publish)(
        f"review_{review_id}", msg.model_dump_json()
    )
    generate_consolidated_report.delay(
        review_id, turn_3_outputs, all_metrics, trace_id=trace_id
    )


async def report_and_metrics_logic(
    review_id: str,
    turn_3_outputs: Dict[str, Any],
    all_metrics: List[List[Dict[str, Any]]],
    trace_id: str,
):
    llm_service = LLMService()
    storage_service = StorageService()

    system_prompt = "You are a Reporter AI..."
    user_prompt = (
        f"Please consolidate...\n{json.dumps(turn_3_outputs, indent=2, ensure_ascii=False)}"
    )

    report_content, _ = await call_llm_with_metrics(
        llm_service.generate_consolidated_report,
        topic="",  # Not needed for the final report
        round_number=3,
        mode="synthesis",
        panel_reports=list(turn_3_outputs.values()),
        request_id=f"{trace_id}-report",
    )
    final_report_data = json.loads(report_content)
    await storage_service.save_final_report(
        review_id=review_id, report_data=final_report_data
    )

    if settings.METRICS_ENABLED:
        # Aggregate overall metrics
        total_duration = sum(m.get("duration_seconds", 0) for r in all_metrics for m in r)
        total_tokens = sum(m.get("total_tokens", 0) for r in all_metrics for m in r)
        cost_per_token = 0.000002
        total_cost = total_tokens * cost_per_token

        # Aggregate per-provider metrics
        provider_metrics = defaultdict(lambda: {"success": 0, "fail": 0, "total_tokens": 0, "duration": 0})
        for round_metric in all_metrics:
            for turn_metric in round_metric:
                provider = turn_metric.get("provider")
                if provider:
                    if turn_metric.get("success"):
                        provider_metrics[provider]["success"] += 1
                    else:
                        provider_metrics[provider]["fail"] += 1
                    provider_metrics[provider]["total_tokens"] += turn_metric.get("total_tokens", 0)
                    provider_metrics[provider]["duration"] += turn_metric.get("duration_seconds", 0)

        metrics_to_save = ReviewMetrics(
            review_id=review_id,
            total_duration_seconds=total_duration,
            total_tokens_used=total_tokens,
            total_cost_usd=total_cost,
            round_metrics=all_metrics,
            provider_metrics=dict(provider_metrics),
            created_at=int(time.time()),
        )
        await storage_service.save_review_metrics(metrics_to_save)
        check_for_alerts(metrics_to_save)


@celery_app.task(bind=True)
def generate_consolidated_report(
    self: Task,
    review_id: str,
    turn_3_outputs: Dict[str, Any],
    all_metrics: List[List[Dict[str, Any]]],
    trace_id: str,
) -> None:
    logger.info(
        f"Generating consolidated report for review: {review_id} with trace_id: {trace_id}"
    )
    async_to_sync(report_and_metrics_logic)(
        review_id, turn_3_outputs, all_metrics, trace_id
    )
    msg = WebSocketMessage(
        type="status_update", review_id=review_id, payload={"status": "completed"}
    )
    async_to_sync(redis_pubsub_manager.publish)(
        f"review_{review_id}", msg.model_dump_json()
    )


from collections import defaultdict

def check_for_alerts(metrics: ReviewMetrics):
    # Overall alerts
    if metrics.total_tokens_used > settings.ALERT_TOKEN_THRESHOLD:
        msg = f"Token threshold breached for review {metrics.review_id}. Used: {metrics.total_tokens_used}, Threshold: {settings.ALERT_TOKEN_THRESHOLD}"
        logger.warning(msg)
        latest_alerts.append({"type": "token_threshold", "message": msg, "ts": time.time()})

    if metrics.total_duration_seconds > settings.ALERT_LATENCY_SECONDS_THRESHOLD:
        msg = f"Latency threshold breached for review {metrics.review_id}. Duration: {metrics.total_duration_seconds:.2f}s, Threshold: {settings.ALERT_LATENCY_SECONDS_THRESHOLD}s"
        logger.warning(msg)
        latest_alerts.append({"type": "latency_threshold", "message": msg, "ts": time.time()})

    # Provider-specific alerts
    provider_stats = defaultdict(lambda: {"success": 0, "fail": 0})
    for round_metric in metrics.round_metrics:
        for turn_metric in round_metric:
            provider = turn_metric.get("provider")
            if provider:
                if turn_metric.get("success"):
                    provider_stats[provider]["success"] += 1
                else:
                    provider_stats[provider]["fail"] += 1

    for provider, stats in provider_stats.items():
        total = stats["success"] + stats["fail"]
        if total > 0:
            failure_rate = stats["fail"] / total
            if failure_rate > settings.ALERT_PROVIDER_FAILURE_RATE_THRESHOLD:
                msg = f"High failure rate for provider '{provider}' on review {metrics.review_id}. Rate: {failure_rate:.2%}, Threshold: {settings.ALERT_PROVIDER_FAILURE_RATE_THRESHOLD:.2%}"
                logger.warning(msg)
                latest_alerts.append({"type": "provider_failure_rate", "provider": provider, "message": msg, "ts": time.time()})

    while len(latest_alerts) > 50:
        latest_alerts.pop(0)
