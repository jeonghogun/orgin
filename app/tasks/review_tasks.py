import logging
import time
import json
import redis
from redis.exceptions import RedisError
from datetime import datetime
from typing import List, Dict, Any, Tuple, Union, Optional, Type

from celery import states
from celery.exceptions import Ignore
from pydantic import BaseModel, ValidationError

from app.celery_app import celery_app
from app.config.settings import get_effective_redis_url, settings
from app.models.schemas import Message, WebSocketMessage
from app.models.review_schemas import (
    LLMReviewInitialAnalysis,
    LLMReviewRebuttal,
    LLMReviewSynthesis,
    LLMReviewResolution,
    LLMFinalReport,
)
from app.services.redis_pubsub import redis_pubsub_manager
from app.services.llm_strategy import llm_strategy_service, ProviderPanelistConfig
from app.services.review_templates import build_final_report_message
from app.services.prompt_service import prompt_service
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

def _save_panelist_message(review_room_id: str, content: str, persona: str, round_num: int) -> Message:
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
    return message

def _check_review_budget(review_id: str, all_metrics: List[List[Dict[str, Any]]]):
    """Checks if the review has exceeded its token budget."""
    if not settings.PER_REVIEW_TOKEN_BUDGET:
        return
    total_tokens = sum(m.get("total_tokens", 0) for r_metrics in all_metrics for m in r_metrics if m)
    if total_tokens > settings.PER_REVIEW_TOKEN_BUDGET:
        error_msg = f"Review {review_id} exceeded token budget of {settings.PER_REVIEW_TOKEN_BUDGET} with {total_tokens} tokens."
        logger.error(error_msg)
        raise BudgetExceededError(error_msg)


def _record_status_update(review_id: str, status: str, round_num: Optional[int] = None) -> None:
    """Persist and broadcast a status update for downstream consumers."""

    timestamp = get_current_timestamp()
    payload = {"status": status}
    event = {
        "review_id": review_id,
        "ts": timestamp,
        "type": "status_update",
        "round": round_num,
        "actor": "system",
        "content": json.dumps(payload),
    }
    try:
        storage_service.log_review_event(event)
    except Exception as exc:
        logger.warning(
            "Failed to persist status event %s for review %s: %s",
            status,
            review_id,
            exc,
            exc_info=True,
        )

    redis_pubsub_manager.publish_sync(
        f"review_{review_id}",
        WebSocketMessage(
            type="status_update",
            review_id=review_id,
            ts=timestamp,
            payload=payload,
        ).model_dump_json(),
    )


def _merge_round_outputs(
    panel_history: Dict[str, Dict[str, Any]], round_num: int, turn_outputs: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Return a new panel history that includes the outputs from the given round."""

    updated_history: Dict[str, Dict[str, Any]] = {
        persona: {str(r): data for r, data in rounds.items()}
        for persona, rounds in panel_history.items()
    }

    for persona, output in turn_outputs.items():
        persona_history = updated_history.setdefault(persona, {})
        persona_history[str(round_num)] = output

    return updated_history


def _all_panelists_declined(turn_outputs: Dict[str, Any]) -> bool:
    """Return True if every panelist flagged that they have no new arguments."""

    if not turn_outputs:
        return False
    return all(bool(output.get("no_new_arguments")) for output in turn_outputs.values())


def _collect_completed_rounds(panel_history: Dict[str, Dict[str, Any]]) -> List[int]:
    """Collect the distinct rounds that have at least one panelist output."""

    rounds = set()
    for persona_rounds in panel_history.values():
        for round_key in persona_rounds.keys():
            try:
                rounds.add(int(round_key))
            except (ValueError, TypeError):
                continue
    return sorted(rounds)

def _process_turn_results(
    review_id: str,
    review_room_id: str,
    round_num: int,
    results: List[Tuple[ProviderPanelistConfig, Union[Tuple[Any, Dict[str, Any]], BaseException]]],
    all_previous_metrics: List[List[Dict[str, Any]]],
    validation_model: Type[BaseModel]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[ProviderPanelistConfig]]:
    """
    Processes results from a single turn, validates against a Pydantic model,
    saves messages, and collects metrics.
    """
    turn_outputs, round_metrics, successful_panelists = {}, [], []
    for panelist_config, result in results:
        persona = panelist_config.persona
        if isinstance(result, BaseException):
            logger.error(f"Panelist {persona} failed in round {round_num}: {result}", exc_info=result)
            round_metrics.append({"persona": persona, "success": False, "error": str(result), "provider": panelist_config.provider})
        else:
            content, metrics = result
            try:
                # First, parse the JSON string
                data = json.loads(content)
                # Then, validate the data against the provided Pydantic model
                validated_data = validation_model.model_validate(data)
                # Store the validated data as a dictionary
                turn_outputs[persona] = validated_data.model_dump()

                round_metrics.append(metrics)
                successful_panelists.append(panelist_config)
                # Save the original, validated JSON content to the database
                saved_message = _save_panelist_message(review_room_id, content, persona, round_num)
                # Publish the new message event to the live stream
                redis_pubsub_manager.publish_sync(
                    f"review_{review_id}",
                    WebSocketMessage(
                        type="new_message",
                        review_id=review_id,
                        payload=saved_message.model_dump()
                    ).model_dump_json()
                )
            except (json.JSONDecodeError, ValidationError) as e:
                error_message = f"Panelist {persona} in round {round_num} returned invalid or non-validating JSON. Error: {e}. Raw content: {content}"
                logger.error(error_message)
                round_metrics.append({"persona": persona, "success": False, "error": "Invalid or non-validating JSON response", "provider": panelist_config.provider})

    _check_review_budget(review_id, all_previous_metrics + [round_metrics])
    return turn_outputs, round_metrics, successful_panelists

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def run_initial_panel_turn(self: BaseTask, review_id: str, review_room_id: str, topic: str, instruction: str, panelists_override: Optional[List[str]], trace_id: str):
    try:
        _record_status_update(review_id, "processing")

        if settings.DAILY_ORG_TOKEN_BUDGET:
            redis_url = get_effective_redis_url()
            redis_client = None
            if redis_url:
                try:
                    redis_client = redis.from_url(redis_url, decode_responses=True)
                    today_key = f"daily_token_usage:{datetime.utcnow().strftime('%Y-%m-%d')}"
                    current_usage = int(redis_client.get(today_key) or 0)
                    if current_usage > settings.DAILY_ORG_TOKEN_BUDGET:
                        raise BudgetExceededError(f"Daily token budget of {settings.DAILY_ORG_TOKEN_BUDGET} exceeded.")
                except RedisError as exc:
                    logger.warning(
                        "Skipping org budget enforcement due to Redis error: %s",
                        exc,
                    )
                finally:
                    if redis_client:
                        redis_client.close()
            else:
                logger.info("Daily org token budget check skipped (Redis unavailable)")

        panel_configs = llm_strategy_service.get_default_panelists()
        if panelists_override:
            panel_configs = [p for p in panel_configs if p.provider in panelists_override]

        try:
            storage_service.update_review(review_id, {"status": "in_progress"})
        except Exception as exc:
            logger.warning(
                "Failed to update review %s status to in_progress: %s",
                review_id,
                exc,
                exc_info=True,
            )

        prompt = prompt_service.get_prompt(
            "review_initial_analysis",
            topic=topic,
            instruction=instruction
        )

        initial_results = [run_panelist_turn(self.llm_service, p_config, prompt, trace_id) for p_config in panel_configs]

        # Implement fallback logic as per README
        final_results = []
        openai_config = next((p for p in panel_configs if p.provider == 'openai'), None)

        for p_config, result in initial_results:
            if isinstance(result, BaseException) and p_config.provider != 'openai' and openai_config:
                logger.warning(f"Panelist {p_config.persona} ({p_config.provider}) failed. Retrying with fallback provider OpenAI.")

                fallback_config = ProviderPanelistConfig(
                    provider='openai',
                    persona=p_config.persona,
                    model=openai_config.model,
                    system_prompt=p_config.system_prompt or openai_config.system_prompt,
                    timeout_s=openai_config.timeout_s,
                    max_retries=0
                )

                fb_p_config, fb_result = run_panelist_turn(self.llm_service, fallback_config, prompt, f"{trace_id}-fallback")
                final_results.append((fb_p_config, fb_result))
            else:
                final_results.append((p_config, result))


        turn_outputs, round_metrics, successful_panelists = _process_turn_results(
            review_id, review_room_id, 1, final_results, [], validation_model=LLMReviewInitialAnalysis
        )

        panel_history = _merge_round_outputs({}, 1, turn_outputs)

        try:
            storage_service.update_review(review_id, {"status": "in_progress", "current_round": 1})
        except Exception as exc:
            logger.warning(
                "Failed to persist round 1 metadata for review %s: %s",
                review_id,
                exc,
                exc_info=True,
            )

        _record_status_update(review_id, "initial_turn_complete", round_num=1)

        run_rebuttal_turn.delay(
            review_id=review_id,
            review_room_id=review_room_id,
            turn_1_outputs=turn_outputs,
            panel_history=panel_history,
            all_metrics=[round_metrics],
            successful_panelists=[p.model_dump() for p in successful_panelists],
            trace_id=trace_id,
        )
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
def run_rebuttal_turn(
    self: BaseTask,
    review_id: str,
    review_room_id: str,
    turn_1_outputs: Dict[str, Any],
    panel_history: Dict[str, Dict[str, Any]],
    all_metrics: List[List[Dict[str, Any]]],
    successful_panelists: List[Dict[str, Any]],
    trace_id: str,
):
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

        # Build custom prompts for each panelist to align with README logic
        all_results = []
        prompts_by_persona: Dict[str, str] = {}
        for p_config in panel_configs:
            # Get the panelist's own previous turn output
            own_turn_output = turn_1_outputs.get(p_config.persona)
            if not own_turn_output:
                continue

            # Get summaries of competitors
            competitor_summaries = [
                summary for persona, summary in zip(turn_1_outputs.keys(), round_1_summaries)
                if persona != p_config.persona
            ]

            # Construct the context as described in the README
            competitor_separator = "\n\n---\n\n"
            competitor_section = competitor_separator.join(competitor_summaries)
            rebuttal_context = f"""Your Round 1 analysis (full text):
{json.dumps(own_turn_output, indent=2)}

---
Summaries of competing Round 1 analyses:
{competitor_section}"""

            prompt = prompt_service.get_prompt(
                "review_rebuttal",
                rebuttal_context=rebuttal_context
            )

            prompts_by_persona[p_config.persona] = prompt
            all_results.append(run_panelist_turn(self.llm_service, p_config, prompt, f"{trace_id}-r2-{p_config.provider}"))

        initial_results = all_results
        
        # Implement fallback logic as per README
        final_results = []
        openai_config = next((p for p in panel_configs if p.provider == 'openai'), None)

        for p_config, result in initial_results:
            if isinstance(result, BaseException) and p_config.provider != 'openai' and openai_config:
                logger.warning(f"Panelist {p_config.persona} ({p_config.provider}) failed in round 2. Retrying with fallback provider OpenAI.")

                fallback_config = ProviderPanelistConfig(
                    provider='openai',
                    persona=p_config.persona,
                    model=openai_config.model,
                    system_prompt=p_config.system_prompt or openai_config.system_prompt,
                    timeout_s=openai_config.timeout_s,
                    max_retries=0
                )

                prompt_text = prompts_by_persona.get(p_config.persona)
                if not prompt_text:
                    logger.warning(
                        "Missing stored rebuttal prompt for %s during fallback; using empty prompt.",
                        p_config.persona,
                    )
                fb_p_config, fb_result = run_panelist_turn(
                    self.llm_service,
                    fallback_config,
                    prompt_text or "",
                    f"{trace_id}-r2-fallback",
                )
                final_results.append((fb_p_config, fb_result))
            else:
                final_results.append((p_config, result))

        turn_outputs, round_metrics, successful_panelists = _process_turn_results(
            review_id, review_room_id, 2, final_results, all_metrics, validation_model=LLMReviewRebuttal
        )

        panel_history = _merge_round_outputs(panel_history, 2, turn_outputs)

        try:
            storage_service.update_review(review_id, {"current_round": 2})
        except Exception as exc:
            logger.warning(
                "Failed to persist round 2 metadata for review %s: %s",
                review_id,
                exc,
                exc_info=True,
            )

        all_metrics.append(round_metrics)
        _record_status_update(review_id, "rebuttal_turn_complete", round_num=2)

        if _all_panelists_declined(turn_outputs):
            _record_status_update(review_id, "no_new_arguments_stop", round_num=2)
            executed_rounds = _collect_completed_rounds(panel_history)
            generate_consolidated_report.delay(
                review_id=review_id,
                panel_history=panel_history,
                all_metrics=all_metrics,
                executed_rounds=executed_rounds,
                trace_id=trace_id,
            )
            return

        run_synthesis_turn.delay(
            review_id=review_id,
            review_room_id=review_room_id,
            turn_1_outputs=turn_1_outputs,
            turn_2_outputs=turn_outputs,
            panel_history=panel_history,
            all_metrics=all_metrics,
            successful_panelists=[p.model_dump() for p in successful_panelists],
            trace_id=trace_id,
        )
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
def run_synthesis_turn(
    self: BaseTask,
    review_id: str,
    review_room_id: str,
    turn_1_outputs: Dict[str, Any],
    turn_2_outputs: Dict[str, Any],
    panel_history: Dict[str, Dict[str, Any]],
    all_metrics: List[List[Dict[str, Any]]],
    successful_panelists: List[Dict[str, Any]],
    trace_id: str,
):
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

        all_results = []
        prompts_by_persona: Dict[str, str] = {}
        for p_config in panel_configs:
            persona = p_config.persona
            own_r1 = turn_1_outputs.get(persona)
            own_r2 = turn_2_outputs.get(persona)
            if not own_r1 or not own_r2:
                continue

            # Summarize competitors' Round 2 outputs
            competitor_r2_context_parts = []
            for p, output in turn_2_outputs.items():
                if p == persona:
                    continue
                agreements = "\n".join(f"- {a}" for a in output.get("agreements", []))
                disagreements = "\n".join(f"- Point: {d['point']}, Reasoning: {d['reasoning']}" for d in output.get("disagreements", []))
                additions = "\n".join(f"- Point: {a['point']}, Reasoning: {a['reasoning']}" for a in output.get("additions", []))
                competitor_r2_context_parts.append(f"""Summary of {p}'s Round 2 Arguments:
Agreements: {agreements}
Disagreements: {disagreements}
Additions: {additions}""")

            competitor_r2_context = "\n\n---\n\n".join(competitor_r2_context_parts)

            synthesis_context = f"""Your own Round 1 and 2 arguments (full text):
Round 1: {json.dumps(own_r1, indent=2)}
Round 2: {json.dumps(own_r2, indent=2)}

---
Summaries of competing Round 2 analyses:
{competitor_r2_context}"""

            prompt = prompt_service.get_prompt(
                "review_synthesis",
                synthesis_context=synthesis_context
            )
            prompts_by_persona[persona] = prompt
            all_results.append(run_panelist_turn(self.llm_service, p_config, prompt, f"{trace_id}-r3-{p_config.provider}"))

        initial_results = all_results

        # Implement fallback logic as per README
        final_results = []
        openai_config = next((p for p in panel_configs if p.provider == 'openai'), None)

        for p_config, result in initial_results:
            if isinstance(result, BaseException) and p_config.provider != 'openai' and openai_config:
                logger.warning(f"Panelist {p_config.persona} ({p_config.provider}) failed in round 3. Retrying with fallback provider OpenAI.")

                fallback_config = ProviderPanelistConfig(
                    provider='openai',
                    persona=p_config.persona,
                    model=openai_config.model,
                    system_prompt=p_config.system_prompt or openai_config.system_prompt,
                    timeout_s=openai_config.timeout_s,
                    max_retries=0
                )

                prompt_text = prompts_by_persona.get(p_config.persona)
                if not prompt_text:
                    logger.warning(
                        "Missing stored synthesis prompt for %s during fallback; using empty prompt.",
                        p_config.persona,
                    )
                fb_p_config, fb_result = run_panelist_turn(
                    self.llm_service,
                    fallback_config,
                    prompt_text or "",
                    f"{trace_id}-r3-fallback",
                )
                final_results.append((fb_p_config, fb_result))
            else:
                final_results.append((p_config, result))

        turn_outputs, round_metrics, successful_panelists = _process_turn_results(
            review_id, review_room_id, 3, final_results, all_metrics, validation_model=LLMReviewSynthesis
        )

        panel_history = _merge_round_outputs(panel_history, 3, turn_outputs)

        try:
            storage_service.update_review(review_id, {"current_round": 3})
        except Exception as exc:
            logger.warning(
                "Failed to persist round 3 metadata for review %s: %s",
                review_id,
                exc,
                exc_info=True,
            )

        all_metrics.append(round_metrics)
        _record_status_update(review_id, "synthesis_turn_complete", round_num=3)

        if _all_panelists_declined(turn_outputs):
            _record_status_update(review_id, "no_new_arguments_stop", round_num=3)
            executed_rounds = _collect_completed_rounds(panel_history)
            generate_consolidated_report.delay(
                review_id=review_id,
                panel_history=panel_history,
                all_metrics=all_metrics,
                executed_rounds=executed_rounds,
                trace_id=trace_id,
            )
            return

        run_resolution_turn.delay(
            review_id=review_id,
            review_room_id=review_room_id,
            panel_history=panel_history,
            round_3_outputs=turn_outputs,
            all_metrics=all_metrics,
            successful_panelists=[p.model_dump() for p in successful_panelists],
            trace_id=trace_id,
        )
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
def run_resolution_turn(
    self: BaseTask,
    review_id: str,
    review_room_id: str,
    panel_history: Dict[str, Dict[str, Any]],
    round_3_outputs: Dict[str, Any],
    all_metrics: List[List[Dict[str, Any]]],
    successful_panelists: List[Dict[str, Any]],
    trace_id: str,
):
    try:
        panel_configs = [ProviderPanelistConfig(**p) for p in successful_panelists]

        all_results = []
        prompts_by_persona: Dict[str, str] = {}
        for p_config in panel_configs:
            persona = p_config.persona
            own_round3 = round_3_outputs.get(persona)
            if not own_round3:
                continue

            earlier_rounds = []
            persona_rounds = panel_history.get(persona, {})
            for round_key in sorted(persona_rounds.keys(), key=lambda r: int(r)):
                if round_key == "3":
                    continue
                try:
                    round_label = int(round_key)
                except (ValueError, TypeError):
                    round_label = round_key
                earlier_rounds.append(
                    f"Round {round_label}:\n{json.dumps(persona_rounds[round_key], indent=2)}"
                )
            earlier_section = "\n\n---\n\n".join(earlier_rounds) if earlier_rounds else "No earlier round context available."

            competitors = []
            for other_persona, output in round_3_outputs.items():
                if other_persona == persona:
                    continue
                recommendations = "\n".join(f"- {rec}" for rec in output.get("recommendations", []))
                competitors.append(
                    f"Panelist: {other_persona}\nExecutive Summary: {output.get('executive_summary', 'N/A')}\nRecommendations:\n{recommendations or '- (none)'}\nFlagged No New Arguments: {output.get('no_new_arguments', False)}"
                )
            competitor_section = "\n\n---\n\n".join(competitors) if competitors else "No competing syntheses were provided."

            resolution_context = f"""Your Round 3 synthesis (full JSON):
{json.dumps(own_round3, indent=2)}

---
Earlier rounds from your perspective:
{earlier_section}

---
Round 3 syntheses from other panelists:
{competitor_section}
"""

            prompt = prompt_service.get_prompt(
                "review_resolution",
                resolution_context=resolution_context,
            )

            prompts_by_persona[persona] = prompt
            all_results.append(
                run_panelist_turn(
                    self.llm_service,
                    p_config,
                    prompt,
                    f"{trace_id}-r4-{p_config.provider}",
                )
            )

        initial_results = all_results

        final_results = []
        openai_config = next((p for p in panel_configs if p.provider == 'openai'), None)

        for p_config, result in initial_results:
            if isinstance(result, BaseException) and p_config.provider != 'openai' and openai_config:
                logger.warning(
                    f"Panelist {p_config.persona} ({p_config.provider}) failed in round 4. Retrying with fallback provider OpenAI."
                )

                fallback_config = ProviderPanelistConfig(
                    provider='openai',
                    persona=p_config.persona,
                    model=openai_config.model,
                    system_prompt=p_config.system_prompt or openai_config.system_prompt,
                    timeout_s=openai_config.timeout_s,
                    max_retries=0
                )

                prompt_text = prompts_by_persona.get(p_config.persona)
                if not prompt_text:
                    logger.warning(
                        "Missing stored resolution prompt for %s during fallback; using empty prompt.",
                        p_config.persona,
                    )
                fb_p_config, fb_result = run_panelist_turn(
                    self.llm_service,
                    fallback_config,
                    prompt_text or "",
                    f"{trace_id}-r4-fallback",
                )
                final_results.append((fb_p_config, fb_result))
            else:
                final_results.append((p_config, result))

        turn_outputs, round_metrics, _ = _process_turn_results(
            review_id,
            review_room_id,
            4,
            final_results,
            all_metrics,
            validation_model=LLMReviewResolution,
        )

        panel_history = _merge_round_outputs(panel_history, 4, turn_outputs)

        try:
            storage_service.update_review(review_id, {"current_round": 4})
        except Exception as exc:
            logger.warning(
                "Failed to persist round 4 metadata for review %s: %s",
                review_id,
                exc,
                exc_info=True,
            )

        all_metrics.append(round_metrics)
        _record_status_update(review_id, "round4_turn_complete", round_num=4)

        executed_rounds = _collect_completed_rounds(panel_history)
        generate_consolidated_report.delay(
            review_id=review_id,
            panel_history=panel_history,
            all_metrics=all_metrics,
            executed_rounds=executed_rounds,
            trace_id=trace_id,
        )
    except BudgetExceededError as e:
        logger.error(f"Failed round 4 turn for review {review_id}: {e}")
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": str(e)}})
        self.update_state(state=states.FAILURE, meta={'exc_type': 'BudgetExceededError', 'exc_message': str(e)})
        raise Ignore()
    except Exception as e:
        logger.error(f"Unhandled error in round 4 for review {review_id}: {e}", exc_info=True)
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "An unexpected error occurred."}})
        raise

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3}, retry_backoff=True)
def generate_consolidated_report(
    self: BaseTask,
    review_id: str,
    panel_history: Dict[str, Dict[str, Any]],
    all_metrics: List[List[Dict[str, Any]]],
    executed_rounds: List[int],
    trace_id: str,
):
    try:
        system_prompt = "You are the Chief Editor. Your task is to synthesize final reports from multiple AI panelists into a single, cohesive, and actionable final report for a key decision-maker. Pay close attention to points of consensus and disagreement."

        panelist_reports = []
        for persona, rounds in panel_history.items():
            sorted_rounds = sorted(
                rounds.items(),
                key=lambda item: int(item[0]) if isinstance(item[0], str) and item[0].isdigit() else item[0],
            )
            normalized_rounds = {str(round_key): data for round_key, data in sorted_rounds}
            panelist_reports.append({"persona": persona, "rounds": normalized_rounds})

        rounds_completed = ", ".join(f"Round {round_num}" for round_num in executed_rounds) or "None"
        if executed_rounds and executed_rounds[-1] < 4:
            rounds_completed = f"{rounds_completed} (stopped early)"

        user_prompt = prompt_service.get_prompt(
            "review_final_report",
            panelist_reports=json.dumps(panelist_reports, indent=2),
            rounds_completed=rounds_completed,
        )
        # Use a powerful model for the final synthesis
        final_report_str, _ = self.llm_service.invoke_sync(
            provider_name="openai",
            model="gpt-4-turbo",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=f"{trace_id}-report",
            response_format="json"
        )

        final_report_json = json.loads(final_report_str)
        final_report_data = LLMFinalReport.model_validate(final_report_json)
        storage_service.save_final_report(review_id=review_id, report_data=final_report_data.model_dump())

        review_meta = storage_service.get_review_meta(review_id)
        if review_meta:
            final_message_content = build_final_report_message(
                review_meta.topic,
                final_report_data.model_dump(),
            )
            try:
                message = Message(
                    message_id=generate_id(),
                    room_id=review_meta.room_id,
                    user_id="observer",
                    role="assistant",
                    content=final_message_content,
                    timestamp=get_current_timestamp(),
                )
                storage_service.save_message(message)
            except Exception as save_error:
                logger.error(
                    "Failed to persist final observer summary for review %s: %s",
                    review_id,
                    save_error,
                    exc_info=True,
                )
            else:
                redis_pubsub_manager.publish_sync(
                    f"review_{review_id}",
                    WebSocketMessage(
                        type="new_message",
                        review_id=review_id,
                        payload=message.model_dump(),
                    ).model_dump_json(),
                )

        if settings.METRICS_ENABLED:
            total_tokens = sum(m.get("total_tokens", 0) for r in all_metrics for m in r if m)
            if settings.DAILY_ORG_TOKEN_BUDGET:
                redis_url = get_effective_redis_url()
                redis_client = None
                if redis_url:
                    try:
                        redis_client = redis.from_url(redis_url, decode_responses=True)
                        today_key = f"daily_token_usage:{datetime.utcnow().strftime('%Y-%m-%d')}"
                        redis_client.incrby(today_key, total_tokens)
                        redis_client.expire(today_key, 60 * 60 * 25)
                    except RedisError as exc:
                        logger.warning("Failed to update daily org usage in Redis: %s", exc)
                    finally:
                        if redis_client:
                            redis_client.close()
                else:
                    logger.info("Daily org token usage tracking skipped (Redis unavailable)")

        _record_status_update(review_id, "completed")
    except Exception as e:
        logger.error(f"Error generating consolidated report for review {review_id}: {e}", exc_info=True)
        storage_service.update_review(review_id, {"status": "failed", "final_report": {"error": "Failed to generate final report."}})
        raise
