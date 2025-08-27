import logging
import time
import json
import asyncio
from typing import List, Dict, Any, Callable, Awaitable, Tuple, Union
from celery import Task
from app.celery_app import celery_app
from app.config.settings import settings
from app.services.llm_service import LLMService
from app.services.storage_service import StorageService
from app.models.schemas import ReviewMetrics

logger = logging.getLogger(__name__)

PANELIST_PERSONAS = ["AGI 비관론자", "AGI 낙관론자", "AGI 중립론자"]
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


async def initial_turn_logic(
    review_id: str, topic: str, instruction: str, request_id: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm_service = LLMService()
    storage_service = StorageService()
    turn_1_outputs: Dict[str, Any] = {}
    round_1_metrics: List[Dict[str, Any]] = []
    tasks: List[Awaitable[Tuple[Any, Dict[str, Any]]]] = []
    for persona in PANELIST_PERSONAS:
        tasks.append(
            call_llm_with_metrics(
                llm_service.generate_panel_analysis,
                topic=topic,
                persona=persona,
                instruction=instruction,
                request_id=f"{request_id}-{persona}",
            )
        )

    results: List[Union[Tuple[Any, Dict[str, Any]], BaseException]] = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        persona = PANELIST_PERSONAS[i]
        if isinstance(result, BaseException):
            logger.error(f"Error generating initial turn for {persona}: {result}")
            turn_1_outputs[persona] = {"error": str(result)}
            round_1_metrics.append(
                {"persona": persona, "success": False, "error": str(result)}
            )
        else:
            content, metrics = result
            turn_1_outputs[persona] = json.loads(content)
            metrics["persona"] = persona
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


@celery_app.task(bind=True)
def run_initial_panel_turn(self, review_id: str, topic: str, instruction: str):  # type: ignore
    logger.info(f"Starting initial panel turn for review: {review_id}")
    turn_outputs, round_metrics = asyncio.run(
        initial_turn_logic(review_id, topic, instruction, str(self.request.id))  # type: ignore
    )
    run_rebuttal_turn.apply_async(args=(review_id, turn_outputs, round_metrics))


async def rebuttal_turn_logic(
    review_id: str, turn_1_outputs: Dict[str, Any], request_id: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm_service = LLMService()
    storage_service = StorageService()
    turn_2_outputs: Dict[str, Any] = {}
    round_2_metrics: List[Dict[str, Any]] = []

    tasks: List[Awaitable[Tuple[Any, Dict[str, Any]]]] = []
    for current_persona in PANELIST_PERSONAS:
        own_previous_output = turn_1_outputs.get(current_persona, {})

        peer_summaries: List[str] = []
        for peer_persona, peer_output in turn_1_outputs.items():
            if peer_persona != current_persona:
                summary, _ = await call_llm_with_metrics(
                    llm_service.summarize_for_debate,
                    panelist_output=json.dumps(peer_output),
                    request_id=f"{request_id}-summary-{peer_persona}",
                )
                peer_summaries.append(f"--- {peer_persona}'s Summary ---\n{summary}\n")

        system_prompt = f"""You are {current_persona}, continuing a debate. You are in Turn 2 (Rebuttal). Your goal is to respond to your peers' arguments from Turn 1. Maintain your persona and be consistent with your previous arguments."""
        user_prompt = f"""Your previous output (full text):\n{json.dumps(own_previous_output)}\n\nSummaries of your peers' outputs:\n{''.join(peer_summaries)}\n\nPlease provide your rebuttal and analysis."""

        tasks.append(
            call_llm_with_metrics(
                llm_service.generate_panel_analysis,
                topic="", # Topic is not needed for rebuttal
                persona=current_persona,
                instruction=user_prompt, # Pass the full context as instruction
                request_id=f"{request_id}-{current_persona}",
            )
        )

    results: List[Union[Tuple[Any, Dict[str, Any]], BaseException]] = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        current_persona = PANELIST_PERSONAS[i]
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
    self: Task[..., Any],
    review_id: str,
    turn_1_outputs: Dict[str, Any],
    round_1_metrics: List[Dict[str, Any]],
) -> None:
    logger.info(f"Starting rebuttal turn for review: {review_id}")
    turn_2_outputs, round_2_metrics = asyncio.run(
        rebuttal_turn_logic(review_id, turn_1_outputs, str(self.request.id))
    )
    all_metrics: List[List[Dict[str, Any]]] = [round_1_metrics, round_2_metrics]
    run_synthesis_turn.apply_async(
        args=(review_id, turn_1_outputs, turn_2_outputs, all_metrics)
    )


async def synthesis_turn_logic(
    review_id: str,
    turn_1_outputs: Dict[str, Any],
    turn_2_outputs: Dict[str, Any],
    request_id: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm_service = LLMService()
    storage_service = StorageService()
    turn_3_outputs: Dict[str, Any] = {}
    round_3_metrics: List[Dict[str, Any]] = []

    tasks: List[Awaitable[Tuple[Any, Dict[str, Any]]]] = []
    for current_persona in PANELIST_PERSONAS:
        own_turn_1_output = turn_1_outputs.get(current_persona, {})
        own_turn_2_output = turn_2_outputs.get(current_persona, {})

        peer_summaries: List[str] = []
        for peer_persona, peer_output in turn_2_outputs.items():
            if peer_persona != current_persona:
                summary, _ = await call_llm_with_metrics(
                    llm_service.summarize_for_debate,
                    panelist_output=json.dumps(peer_output),
                    request_id=f"{request_id}-summary-{peer_persona}",
                )
                peer_summaries.append(
                    f"--- {peer_persona}'s Turn 2 Summary ---\n{summary}\n"
                )

        system_prompt = f"""You are {current_persona}, in the final turn of a debate (Turn 3: Synthesis). Your goal is to produce a final, synthesized opinion that considers your previous points and the rebuttals from your peers."""
        user_prompt = f"""Your Turn 1 Output:\n{json.dumps(own_turn_1_output)}\nYour Turn 2 Rebuttal:\n{json.dumps(own_turn_2_output)}\n\nSummaries of your peers' Turn 2 Rebuttals:\n{''.join(peer_summaries)}\n\nPlease provide your final, synthesized analysis."""

        tasks.append(
            call_llm_with_metrics(
                llm_service.generate_panel_analysis,
                topic="", # Topic is not needed for synthesis
                persona=current_persona,
                instruction=user_prompt, # Pass the full context as instruction
                request_id=f"{request_id}-{current_persona}",
            )
        )

    results: List[Union[Tuple[Any, Dict[str, Any]], BaseException]] = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        current_persona = PANELIST_PERSONAS[i]
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
    self: Task[..., Any],
    review_id: str,
    turn_1_outputs: Dict[str, Any],
    turn_2_outputs: Dict[str, Any],
    all_metrics: List[List[Dict[str, Any]]],
) -> None:
    logger.info(f"Starting synthesis turn for review: {review_id}")
    turn_3_outputs, round_3_metrics = asyncio.run(
        synthesis_turn_logic(
            review_id, turn_1_outputs, turn_2_outputs, str(self.request.id)
        )
    )
    all_metrics.append(round_3_metrics)
    generate_consolidated_report.apply_async(
        args=(review_id, turn_3_outputs, all_metrics)
    )


async def report_and_metrics_logic(
    review_id: str,
    turn_3_outputs: Dict[str, Any],
    all_metrics: List[List[Dict[str, Any]]],
    request_id: str,
):
    llm_service = LLMService()
    storage_service = StorageService()

    system_prompt = "You are a Reporter AI..."
    user_prompt = (
        f"Please consolidate...\n{json.dumps(turn_3_outputs, indent=2, ensure_ascii=False)}"
    )

    report_content, _ = await call_llm_with_metrics(
        llm_service.generate_consolidated_report,
        topic="", # Not needed for the final report
        round_number=3,
        mode="synthesis",
        panel_reports=list(turn_3_outputs.values()),
        request_id=f"{request_id}-report",
    )
    final_report_data = json.loads(report_content)
    await storage_service.save_final_report(
        review_id=review_id, report_data=final_report_data
    )

    if settings.METRICS_ENABLED:
        total_duration = sum(
            m["duration_seconds"] for r in all_metrics for m in r if m.get("success")
        )
        total_tokens = sum(
            m["total_tokens"] for r in all_metrics for m in r if m.get("success")
        )
        cost_per_token = 0.000002
        total_cost = total_tokens * cost_per_token
        metrics_to_save = ReviewMetrics(
            review_id=review_id,
            total_duration_seconds=total_duration,
            total_tokens_used=total_tokens,
            total_cost_usd=total_cost,
            round_metrics=all_metrics,
            created_at=int(time.time()),
        )
        await storage_service.save_review_metrics(metrics_to_save)
        check_for_alerts(metrics_to_save)


@celery_app.task(bind=True)
def generate_consolidated_report(
    self: Task[..., Any],
    review_id: str,
    turn_3_outputs: Dict[str, Any],
    all_metrics: List[List[Dict[str, Any]]],
) -> None:
    logger.info(f"Generating consolidated report for review: {review_id}")
    asyncio.run(
        report_and_metrics_logic(
            review_id, turn_3_outputs, all_metrics, str(self.request.id)
        )
    )


def check_for_alerts(metrics: ReviewMetrics):
    if metrics.total_tokens_used > settings.ALERT_TOKEN_THRESHOLD:
        msg = f"Token threshold breached for review {metrics.review_id}. Used: {metrics.total_tokens_used}, Threshold: {settings.ALERT_TOKEN_THRESHOLD}"
        logger.warning(msg)
        latest_alerts.append(
            {"type": "token_threshold", "message": msg, "ts": time.time()}
        )

    if metrics.total_duration_seconds > settings.ALERT_LATENCY_SECONDS_THRESHOLD:
        msg = f"Latency threshold breached for review {metrics.review_id}. Duration: {metrics.total_duration_seconds:.2f}s, Threshold: {settings.ALERT_LATENCY_SECONDS_THRESHOLD}s"
        logger.warning(msg)
        latest_alerts.append(
            {"type": "latency_threshold", "message": msg, "ts": time.time()}
        )

    while len(latest_alerts) > 50:
        latest_alerts.pop(0)
