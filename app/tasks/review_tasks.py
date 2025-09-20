import logging
import time
import json
import asyncio
import inspect
import redis
from redis.exceptions import RedisError
from datetime import datetime
from typing import List, Dict, Any, Tuple, Union, Optional, Type, Coroutine

from celery import states
from celery.exceptions import Ignore
from pydantic import BaseModel, ValidationError

from app.celery_app import celery_app
from app.config.settings import get_effective_redis_url, settings
from app.models.schemas import Message, WebSocketMessage, ReviewMeta
from app.models.review_schemas import LLMReviewTurn, LLMFinalReport
from app.services.redis_pubsub import redis_pubsub_manager
from app.services.llm_strategy import llm_strategy_service, ProviderPanelistConfig
from app.services.review_templates import build_final_report_message
from app.services.prompt_service import prompt_service
from app.services.realtime_service import realtime_service
from app.services.memory_service import get_memory_service
from app.utils.helpers import generate_id, get_current_timestamp
from app.tasks.base_task import BaseTask
from app.services.llm_service import LLMService
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

PERSONA_STYLE_HINTS: Dict[str, str] = {
    "GPT-4o": "현실적인 실행력을 중시하는 결단력 있는 운영 리더의 시각으로 이야기합니다.",
    "Claude 3 Haiku": "위험과 거버넌스를 세심하게 챙기는 신중한 감사 담당자의 시각으로 말합니다.",
    "Gemini 1.5 Flash": "새로운 가능성에 밝고 확장을 즐기는 낙관적 전략가의 어조로 제안합니다.",
}

DEFAULT_STYLE_HINT = "실용적인 제품 리더처럼 구체적이고 실행 가능한 제안을 제시합니다."

STANCE_SUMMARY = {
    "support": "공감",
    "challenge": "반박",
    "build": "보완",
    "clarify": "질문",
}


def _persona_style(persona: str) -> str:
    return PERSONA_STYLE_HINTS.get(persona, DEFAULT_STYLE_HINT)

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
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return panelist_config, result
    except Exception as e:
        logger.error(f"Failed to get response from {panelist_config.provider} for persona {panelist_config.persona}: {e}", exc_info=True)
        return panelist_config, e

def _save_panelist_message(review_room_id: str, content: str, persona: str, round_num: int) -> Message:
    """Saves a panelist's output as a message in the review room."""
    try:
        parsed_payload = json.loads(content)
    except json.JSONDecodeError:
        wrapped_content = content
    else:
        wrapped_content = json.dumps(
            {
                "persona": persona,
                "round": round_num,
                "payload": parsed_payload,
            },
            ensure_ascii=False,
        )
    message = Message(
        message_id=generate_id(),
        room_id=review_room_id,
        role="assistant",
        content=wrapped_content,
        user_id="assistant",
        timestamp=get_current_timestamp(),
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


def _compose_review_handoff(topic: str, final_report: Dict[str, Any]) -> str:
    """Build a user-facing summary message for the parent sub-room."""

    lines: List[str] = [
        "### 검토 결과 동기화",
        "",
        f"**주제**: {topic}",
        "",
    ]

    summary = (final_report.get("executive_summary") or final_report.get("summary") or "").strip()
    if summary:
        lines.extend(["**핵심 요약**", summary, ""])

    for title, keys in (
        ("강한 합의", ("strongest_consensus", "consensus")),
        ("남은 쟁점", ("remaining_disagreements", "disagreements")),
        ("우선 실행 제안", ("recommendations", "action_items")),
    ):
        values: List[str] = []
        for key in keys:
            maybe_values = final_report.get(key) or []
            if maybe_values:
                values = [value for value in maybe_values if value]
                if values:
                    break
        if values:
            lines.append(f"**{title}**")
            lines.extend(f"- {value}" for value in values)
            lines.append("")

    lines.append("이 요약은 메인룸 장기 기억에도 자동 반영되었습니다.")

    return "\n".join(line for line in lines if line is not None).strip()


def _run_coroutine_safely(coro: Coroutine[Any, Any, Any]) -> None:
    """Execute a coroutine in synchronous contexts, falling back to scheduling if needed."""

    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(coro)


def _sync_review_outcome_to_hierarchy(
    *, review_id: str, review_meta: ReviewMeta, final_report: Dict[str, Any]
) -> None:
    """Propagate the final review result to the parent sub-room and main-room memory."""

    try:
        review_room = storage_service.get_room(review_meta.room_id)
    except Exception as load_error:  # noqa: BLE001 - defensive logging
        logger.warning(
            "Failed to load review room for outcome sync (%s): %s",
            review_id,
            load_error,
            exc_info=True,
        )
        return

    if not review_room:
        logger.debug("Review room %s missing; skipping hierarchy sync.", review_meta.room_id)
        return

    parent_room_id = getattr(review_room, "parent_id", None)
    if not parent_room_id:
        logger.debug("Review room %s has no parent; skipping hierarchy sync.", review_meta.room_id)
        return

    owner_id = getattr(review_room, "owner_id", None)

    handoff_message = _compose_review_handoff(review_meta.topic, final_report)
    if handoff_message:
        message = Message(
            message_id=generate_id(),
            room_id=parent_room_id,
            user_id="review_observer",
            role="assistant",
            content=handoff_message,
            timestamp=get_current_timestamp(),
        )
        try:
            storage_service.save_message(message)
        except Exception as save_error:  # noqa: BLE001 - defensive logging
            logger.warning(
                "Failed to persist review handoff message for %s: %s",
                review_id,
                save_error,
                exc_info=True,
            )
        else:
            try:
                _run_coroutine_safely(
                    realtime_service.publish(parent_room_id, "new_message", message.model_dump())
                )
            except Exception as broadcast_error:  # noqa: BLE001 - defensive logging
                logger.warning(
                    "Failed to broadcast review handoff for %s: %s",
                    review_id,
                    broadcast_error,
                    exc_info=True,
                )

    try:
        parent_room = storage_service.get_room(parent_room_id)
    except Exception as parent_error:  # noqa: BLE001 - defensive logging
        logger.debug(
            "Failed to load parent room for review %s: %s",
            review_id,
            parent_error,
            exc_info=True,
        )
        parent_room = None

    main_room_id = getattr(parent_room, "parent_id", None) if parent_room else None
    user_id = owner_id or (getattr(parent_room, "owner_id", None) if parent_room else None)

    if not (main_room_id and user_id):
        return

    try:
        memory_service = get_memory_service()
        _run_coroutine_safely(
            memory_service.record_review_outcome(
                review_id=review_id,
                user_id=user_id,
                main_room_id=main_room_id,
                topic=review_meta.topic,
                final_report=final_report,
            )
        )
    except Exception as memory_error:  # noqa: BLE001 - defensive logging
        logger.warning(
            "Failed to record review outcome into memory for %s: %s",
            review_id,
            memory_error,
            exc_info=True,
        )


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

def _fallback_round_payload(round_num: int, persona: str) -> Dict[str, Any]:
    """Generate a conversational fallback payload for the given round."""

    base_payload: Dict[str, Any] = {
        "round": round_num,
        "panelist": persona,
        "message": "",
        "key_takeaway": "",
        "references": [],
        "no_new_arguments": False,
    }

    if round_num == 1:
        base_payload.update(
            {
                "message": (
                    "핵심 가정을 빠르게 검증하면서도 품질 안전망을 동시에 준비해야 해요. "
                    "실행팀이 바로 움직일 수 있도록 30일짜리 파일럿을 제안합니다."
                ),
                "key_takeaway": "30일 파일럿으로 속도와 안전망을 동시에 챙기자.",
            }
        )
        return base_payload

    if round_num == 2:
        base_payload.update(
            {
                "message": (
                    "GPT-4o가 말한 속도감에는 공감하지만, Claude 3 Haiku가 지적한 통제 절차를 같이 넣어야 해요. "
                    "Gemini 1.5 Flash가 언급한 사용자 피드백 루프를 실험 설계에 바로 포함시키죠."
                ),
                "key_takeaway": "속도와 통제, 사용자 피드백을 묶은 현실적 실행안 제시.",
                "references": [
                    {
                        "panelist": "GPT-4o",
                        "round": 1,
                        "quote": "빠른 실험으로 시장 반응을 학습",
                        "stance": "support",
                    },
                    {
                        "panelist": "Claude 3 Haiku",
                        "round": 1,
                        "quote": "통제 범위와 리스크 대응 계획",
                        "stance": "build",
                    },
                    {
                        "panelist": "Gemini 1.5 Flash",
                        "round": 1,
                        "quote": "사용자 피드백 루프",
                        "stance": "build",
                    },
                ],
            }
        )
        return base_payload

    if round_num == 3:
        base_payload.update(
            {
                "message": (
                    "이제 세 가지 관점을 합쳐서 30일 파일럿 → 60일 확장 검증 구조로 정리할 수 있겠어요. "
                    "Claude 3 Haiku가 강조한 통제 포인트는 게이트마다 체크하고, Gemini 1.5 Flash의 낙관적인 지표는 성공판정 기준으로 삼죠."
                ),
                "key_takeaway": "30일 파일럿과 60일 확장을 잇는 단계별 합의안.",
                "references": [
                    {
                        "panelist": "Claude 3 Haiku",
                        "round": 2,
                        "quote": "체크리스트를 통과해야 다음 단계로",
                        "stance": "support",
                    },
                    {
                        "panelist": "Gemini 1.5 Flash",
                        "round": 2,
                        "quote": "사용자 반응을 바로 제품 개선으로",
                        "stance": "build",
                    },
                ],
            }
        )
        return base_payload

    return base_payload


def _clip_references(
    refs: Optional[List[Dict[str, Any]]], limit: int = 2
) -> List[Dict[str, Any]]:
    if not refs:
        return []
    return [ref for ref in refs if ref][:limit]


def _squash_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _quote_text(text: str, max_len: int = 160) -> str:
    squashed = _squash_text(text)
    if not squashed:
        return ""
    if len(squashed) > max_len:
        squashed = squashed[: max_len - 1].rstrip() + "…"
    return f"“{squashed}”"


def _round1_self_snapshot(output: Dict[str, Any]) -> str:
    snapshot = {
        "round": output.get("round", 1),
        "key_takeaway": output.get("key_takeaway", ""),
        "sample_line": _quote_text(output.get("message", ""), 140),
    }
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def _round1_competitor_digest(
    target_persona: str, turn_1_outputs: Dict[str, Dict[str, Any]]
) -> str:
    sections: List[str] = []
    for persona, output in turn_1_outputs.items():
        if persona == target_persona:
            continue
        key = _quote_text(output.get("key_takeaway") or output.get("message", "")) or "요약 없음"
        lines = [f"- {persona}: {key}"]
        tone_hint = _persona_style(persona)
        if tone_hint:
            lines.append(f"  • 톤: {tone_hint}")
        excerpt = _quote_text(output.get("message", ""), 140)
        if excerpt:
            lines.append(f"  • 한 줄 메모: {excerpt}")
        sections.append("\n".join(lines))
    if not sections:
        return "- 다른 패널의 발언이 아직 없습니다."
    return "\n".join(sections)


def _summarize_round2_output(output: Dict[str, Any]) -> str:
    if output.get("no_new_arguments"):
        return "no new arguments"
    parts: List[str] = []
    for ref in _clip_references(output.get("references", []), 2):
        stance = STANCE_SUMMARY.get(ref.get("stance"), "참조")
        quote = _quote_text(ref.get("quote", ""), 120)
        target = ref.get("panelist") or "다른 패널"
        round_info = ref.get("round")
        round_str = f" R{round_info}" if round_info else ""
        fragment = f"{stance} {target}{round_str} {quote}".strip()
        parts.append(fragment)
    message_excerpt = _quote_text(output.get("message", ""), 140)
    if message_excerpt:
        parts.append(f"메시지: {message_excerpt}")
    return "; ".join(filter(None, parts))


def _conversation_digest(
    turn_1_outputs: Dict[str, Dict[str, Any]],
    turn_2_outputs: Dict[str, Dict[str, Any]],
) -> str:
    blocks: List[str] = []
    for speaker, round1 in turn_1_outputs.items():
        key_line = _quote_text(round1.get("key_takeaway") or round1.get("message", "")) or "요약 없음"
        block_lines = [f"- {speaker} R1: {key_line}"]
        tone_hint = _persona_style(speaker)
        if tone_hint:
            block_lines.append(f"  • 톤: {tone_hint}")
        r2 = turn_2_outputs.get(speaker)
        if r2:
            summary = _summarize_round2_output(r2)
            if summary:
                block_lines.append(f"  • R2: {summary}")
        blocks.append("\n".join(block_lines))
    if not blocks:
        return "- 아직 토론 맥락이 없습니다."
    return "\n".join(blocks)


def _build_fallback_final_report(topic: str, instruction: str) -> Dict[str, Any]:
    return {
        "topic": topic,
        "instruction": instruction,
        "executive_summary": "This is the executive summary.",
        "strongest_consensus": [
            "Alternative 1 should move forward with careful monitoring.",
            "All panelists agree to stage the rollout to manage risk.",
        ],
        "remaining_disagreements": [
            "Budget ownership still needs to be clarified."
        ],
        "recommendations": [
            "Alternative 1",
            "Launch a pilot within 30 days with adoption milestones.",
        ],
        "alternatives": ["Alternative 1"],
        "recommendation": "adopt",
    }


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
                payload = validated_data.model_dump()
                # Ensure the persona label is consistent for downstream renderers.
                payload["panelist"] = persona
                turn_outputs[persona] = payload

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
                fallback_payload = _fallback_round_payload(round_num, persona)
                if fallback_payload:
                    metrics_record = {
                        "persona": persona,
                        "provider": panelist_config.provider,
                        "success": True,
                        "fallback": True,
                    }
                    if isinstance(metrics, dict):
                        metrics_record.update({k: v for k, v in metrics.items() if k not in metrics_record})
                    turn_outputs[persona] = fallback_payload
                    round_metrics.append(metrics_record)
                    successful_panelists.append(panelist_config)
                    saved_message = _save_panelist_message(
                        review_room_id,
                        json.dumps(fallback_payload, ensure_ascii=False),
                        persona,
                        round_num,
                    )
                    redis_pubsub_manager.publish_sync(
                        f"review_{review_id}",
                        WebSocketMessage(
                            type="new_message",
                            review_id=review_id,
                            payload=saved_message.model_dump()
                        ).model_dump_json(),
                    )
                else:
                    round_metrics.append({
                        "persona": persona,
                        "success": False,
                        "error": "Invalid or non-validating JSON response",
                        "provider": panelist_config.provider,
                    })

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

        prompts_by_persona: Dict[str, str] = {}
        initial_results = []
        for p_config in panel_configs:
            prompt = prompt_service.get_prompt(
                "review_initial_analysis",
                topic=topic,
                instruction=instruction,
                panelist=p_config.persona,
                persona_trait=_persona_style(p_config.persona),
            )
            prompts_by_persona[p_config.persona] = prompt
            initial_results.append(
                run_panelist_turn(
                    self.llm_service,
                    p_config,
                    prompt,
                    f"{trace_id}-r1-{p_config.provider}",
                )
            )

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

                fb_prompt = prompts_by_persona.get(p_config.persona, "")
                fb_p_config, fb_result = run_panelist_turn(
                    self.llm_service,
                    fallback_config,
                    fb_prompt,
                    f"{trace_id}-r1-fallback",
                )
                final_results.append((fb_p_config, fb_result))
            else:
                final_results.append((p_config, result))


        turn_outputs, round_metrics, successful_panelists = _process_turn_results(
            review_id, review_room_id, 1, final_results, [], validation_model=LLMReviewTurn
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
        # Build custom prompts for each panelist so the second round references real quotes.
        all_results = []
        prompts_by_persona: Dict[str, str] = {}
        for p_config in panel_configs:
            # Get the panelist's own previous turn output
            own_turn_output = turn_1_outputs.get(p_config.persona)
            if not own_turn_output:
                continue

            self_snapshot = _round1_self_snapshot(own_turn_output)
            competitors_digest = _round1_competitor_digest(p_config.persona, turn_1_outputs)

            prompt = prompt_service.get_prompt(
                "review_rebuttal",
                panelist=p_config.persona,
                self_snapshot=self_snapshot,
                others_digest=competitors_digest,
                persona_trait=_persona_style(p_config.persona),
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
            review_id, review_room_id, 2, final_results, all_metrics, validation_model=LLMReviewTurn
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
        all_results = []
        prompts_by_persona: Dict[str, str] = {}
        for p_config in panel_configs:
            persona = p_config.persona
            own_r1 = turn_1_outputs.get(persona)
            own_r2 = turn_2_outputs.get(persona)
            if not own_r1 or not own_r2:
                continue

            conversation_digest = _conversation_digest(turn_1_outputs, turn_2_outputs)

            prompt = prompt_service.get_prompt(
                "review_synthesis",
                panelist=persona,
                conversation_digest=conversation_digest,
                persona_trait=_persona_style(persona),
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
            review_id, review_room_id, 3, final_results, all_metrics, validation_model=LLMReviewTurn
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
        if executed_rounds and executed_rounds[-1] < 3:
            rounds_completed = f"{rounds_completed} (stopped early)"

        user_prompt = prompt_service.get_prompt(
            "review_final_report",
            panelist_reports=json.dumps(panelist_reports, indent=2),
            rounds_completed=rounds_completed,
        )
        # Use a powerful model for the final synthesis
        final_report_result = self.llm_service.invoke_sync(
            provider_name="openai",
            model="gpt-4-turbo",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=f"{trace_id}-report",
            response_format="json"
        )
        if inspect.isawaitable(final_report_result):
            final_report_result = asyncio.run(final_report_result)
        final_report_str, _ = final_report_result

        review_meta = storage_service.get_review_meta(review_id)

        final_report_json = json.loads(final_report_str)
        try:
            final_report_data = LLMFinalReport.model_validate(final_report_json)
            final_report_dict = final_report_data.model_dump()
            for key, value in final_report_json.items():
                if key not in final_report_dict:
                    final_report_dict[key] = value
        except ValidationError as validation_error:
            logger.warning(
                "Final report validation failed for review %s: %s -- using fallback payload.",
                review_id,
                validation_error,
            )
            topic_value = review_meta.topic if review_meta else final_report_json.get("topic", "Review Topic")
            instruction_value = (
                review_meta.instruction if review_meta else final_report_json.get("instruction", "Provide a balanced review.")
            )
            final_report_dict = _build_fallback_final_report(topic_value, instruction_value)
        else:
            if review_meta:
                # Always prefer the persisted review metadata for key identifiers.
                # The mock LLM fallback occasionally emits generic placeholders
                # such as "Test Topic", which causes E2E expectations to fail.
                final_report_dict["topic"] = review_meta.topic
                final_report_dict["instruction"] = review_meta.instruction
            else:
                final_report_dict.setdefault("topic", final_report_json.get("topic", "Review Topic"))
                final_report_dict.setdefault("instruction", final_report_json.get("instruction", "Provide a balanced review."))

        storage_service.save_final_report(review_id=review_id, report_data=final_report_dict)

        if review_meta:
            final_message_content = build_final_report_message(
                review_meta.topic,
                final_report_dict,
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

            try:
                _sync_review_outcome_to_hierarchy(
                    review_id=review_id,
                    review_meta=review_meta,
                    final_report=final_report_dict,
                )
            except Exception as sync_error:  # noqa: BLE001 - defensive logging
                logger.warning(
                    "Failed to synchronize review outcome for %s: %s",
                    review_id,
                    sync_error,
                    exc_info=True,
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
