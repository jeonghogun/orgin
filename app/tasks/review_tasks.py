import logging
import time
import json
import asyncio
from uuid import uuid4
from celery import chain
from app.celery_app import celery_app
from app.services.llm_service import llm_service
from app.services.storage_service import storage_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

PANELIST_PERSONAS = ["AGI 비관론자", "AGI 낙관론자", "AGI 중립론자"]
latest_alerts = []

async def call_llm_with_metrics(llm_function, **kwargs):
    # ... (implementation from before)
    pass

async def initial_turn_logic(review_id, topic, instruction, request_id):
    # ... (implementation from before)
    pass

@celery_app.task(bind=True)
def run_initial_panel_turn(self, review_id: str, topic: str, instruction: str):
    logger.info(f"Starting initial panel turn for review: {review_id}")
    turn_outputs, round_metrics = asyncio.run(initial_turn_logic(review_id, topic, instruction, self.request.id))
    run_rebuttal_turn.apply_async(args=[review_id, turn_outputs, round_metrics])

async def rebuttal_turn_logic(review_id, turn_1_outputs, request_id):
    turn_2_outputs = {}
    round_2_metrics = []
    for current_persona in PANELIST_PERSONAS:
        own_previous_output = turn_1_outputs.get(current_persona, {})

        peer_summaries = []
        for peer_persona, peer_output in turn_1_outputs.items():
            if peer_persona != current_persona:
                summary, _ = await call_llm_with_metrics(
                    llm_service.summarize_for_debate,
                    panelist_output=json.dumps(peer_output),
                    request_id=f"{request_id}-summary-{peer_persona}"
                )
                peer_summaries.append(f"--- {peer_persona}'s Summary ---\n{summary}\n")

        system_prompt = f"""You are {current_persona}, continuing a debate. You are in Turn 2 (Rebuttal). Your goal is to respond to your peers' arguments from Turn 1. Maintain your persona and be consistent with your previous arguments."""
        user_prompt = f"""Your previous output (full text):\n{json.dumps(own_previous_output)}\n\nSummaries of your peers' outputs:\n{''.join(peer_summaries)}\n\nPlease provide your rebuttal and analysis."""

        try:
            content, metrics = await call_llm_with_metrics(
                llm_service.get_provider().invoke, model=settings.LLM_MODEL,
                system_prompt=system_prompt, user_prompt=user_prompt, request_id=f"{request_id}-{current_persona}"
            )
            turn_2_outputs[current_persona] = json.loads(content)
            metrics["persona"] = current_persona
            round_2_metrics.append(metrics)
            await storage_service.log_review_event({"review_id": review_id, "ts": time.time(), "type": "panel_output", "round": 2, "actor": current_persona, "content": content})
        except Exception as e:
            logger.error(f"Error generating rebuttal for {current_persona}: {e}")
            turn_2_outputs[current_persona] = {"error": str(e)}
            round_2_metrics.append({"persona": current_persona, "success": False, "error": str(e)})
    return turn_2_outputs, round_2_metrics

@celery_app.task(bind=True)
def run_rebuttal_turn(self, review_id: str, turn_1_outputs: dict, round_1_metrics: list):
    logger.info(f"Starting rebuttal turn for review: {review_id}")
    turn_2_outputs, round_2_metrics = asyncio.run(rebuttal_turn_logic(review_id, turn_1_outputs, self.request.id))
    all_metrics = [round_1_metrics, round_2_metrics]
    run_synthesis_turn.apply_async(args=[review_id, turn_1_outputs, turn_2_outputs, all_metrics])

async def synthesis_turn_logic(review_id, turn_1_outputs, turn_2_outputs, request_id):
    turn_3_outputs = {}
    round_3_metrics = []
    for current_persona in PANELIST_PERSONAS:
        own_turn_1_output = turn_1_outputs.get(current_persona, {})
        own_turn_2_output = turn_2_outputs.get(current_persona, {})

        peer_summaries = []
        for peer_persona, peer_output in turn_2_outputs.items():
            if peer_persona != current_persona:
                summary, _ = await call_llm_with_metrics(
                    llm_service.summarize_for_debate,
                    panelist_output=json.dumps(peer_output),
                    request_id=f"{request_id}-summary-{peer_persona}"
                )
                peer_summaries.append(f"--- {peer_persona}'s Turn 2 Summary ---\n{summary}\n")

        system_prompt = f"""You are {current_persona}, in the final turn of a debate (Turn 3: Synthesis). Your goal is to produce a final, synthesized opinion that considers your previous points and the rebuttals from your peers."""
        user_prompt = f"""Your Turn 1 Output:\n{json.dumps(own_turn_1_output)}\nYour Turn 2 Rebuttal:\n{json.dumps(own_turn_2_output)}\n\nSummaries of your peers' Turn 2 Rebuttals:\n{''.join(peer_summaries)}\n\nPlease provide your final, synthesized analysis."""

        try:
            content, metrics = await call_llm_with_metrics(
                llm_service.get_provider().invoke, model=settings.LLM_MODEL,
                system_prompt=system_prompt, user_prompt=user_prompt, request_id=f"{request_id}-{current_persona}"
            )
            turn_3_outputs[current_persona] = json.loads(content)
            metrics["persona"] = current_persona
            round_3_metrics.append(metrics)
            await storage_service.log_review_event({"review_id": review_id, "ts": time.time(), "type": "panel_output", "round": 3, "actor": current_persona, "content": content})
        except Exception as e:
            logger.error(f"Error generating synthesis for {current_persona}: {e}")
            turn_3_outputs[current_persona] = {"error": str(e)}
            round_3_metrics.append({"persona": current_persona, "success": False, "error": str(e)})
    return turn_3_outputs, round_3_metrics

@celery_app.task(bind=True)
def run_synthesis_turn(self, review_id: str, turn_1_outputs: dict, turn_2_outputs: dict, all_metrics: list):
    logger.info(f"Starting synthesis turn for review: {review_id}")
    turn_3_outputs, round_3_metrics = asyncio.run(synthesis_turn_logic(review_id, turn_1_outputs, turn_2_outputs, self.request.id))
    all_metrics.append(round_3_metrics)
    generate_consolidated_report.apply_async(args=[review_id, turn_3_outputs, all_metrics])

async def report_and_metrics_logic(review_id, turn_3_outputs, all_metrics, request_id):
    from app.models.schemas import ReviewMetrics
    # 1. Generate the final text report
    system_prompt = "You are a Reporter AI..."
    user_prompt = f"Please consolidate...\n{json.dumps(turn_3_outputs, indent=2, ensure_ascii=False)}"

    report_content, _ = await call_llm_with_metrics(
        llm_service.get_provider().invoke, model=settings.LLM_MODEL,
        system_prompt=system_prompt, user_prompt=user_prompt, request_id=f"{request_id}-report",
        response_format="json"
    )
    final_report_data = json.loads(report_content)
    await storage_service.save_final_report(review_id=review_id, report_data=final_report_data)

    # 2. Aggregate and save metrics
    if settings.METRICS_ENABLED:
        total_duration = sum(m['duration_seconds'] for r in all_metrics for m in r if m.get('success'))
        total_tokens = sum(m['total_tokens'] for r in all_metrics for m in r if m.get('success'))
        cost_per_token = 0.000002
        total_cost = total_tokens * cost_per_token
        metrics_to_save = ReviewMetrics(
            review_id=review_id, total_duration_seconds=total_duration,
            total_tokens_used=total_tokens, total_cost_usd=total_cost,
            round_metrics=all_metrics, created_at=int(time.time())
        )
        await storage_service.save_review_metrics(metrics_to_save)
        check_for_alerts(metrics_to_save)

@celery_app.task(bind=True)
def generate_consolidated_report(self, review_id: str, turn_3_outputs: dict, all_metrics: list):
    logger.info(f"Generating consolidated report for review: {review_id}")
    asyncio.run(report_and_metrics_logic(review_id, turn_3_outputs, all_metrics, self.request.id))

def check_for_alerts(metrics: "ReviewMetrics"):
    """
    Checks the completed review's metrics against configured thresholds and creates alerts.
    """
    if metrics.total_tokens_used > settings.ALERT_TOKEN_THRESHOLD:
        msg = f"Token threshold breached for review {metrics.review_id}. Used: {metrics.total_tokens_used}, Threshold: {settings.ALERT_TOKEN_THRESHOLD}"
        logger.warning(msg)
        latest_alerts.append({"type": "token_threshold", "message": msg, "ts": time.time()})

    if metrics.total_duration_seconds > settings.ALERT_LATENCY_SECONDS_THRESHOLD:
        msg = f"Latency threshold breached for review {metrics.review_id}. Duration: {metrics.total_duration_seconds:.2f}s, Threshold: {settings.ALERT_LATENCY_SECONDS_THRESHOLD}s"
        logger.warning(msg)
        latest_alerts.append({"type": "latency_threshold", "message": msg, "ts": time.time()})

    # Keep the alerts list from growing indefinitely
    while len(latest_alerts) > 50:
        latest_alerts.pop(0)
