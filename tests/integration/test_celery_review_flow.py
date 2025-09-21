import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from app.tasks.review_tasks import ProviderPanelistConfig


@pytest.mark.asyncio
async def test_create_review_starts_celery_flow(celery_review_client: TestClient, monkeypatch):
    """Ensure that creating a review executes the Celery task chain in eager mode."""

    from app.tasks import review_tasks

    def _mock_panelists():
        return [
            ProviderPanelistConfig(
                provider="openai",
                persona="GPT-4o",
                model="gpt-4o-mini",
                system_prompt="You are a decisive reviewer.",
            )
        ]

    def _stub_run_panelist_turn(llm_service, panelist_config, prompt, request_id):
        round_num = 1
        if "-r2" in request_id:
            round_num = 2
        elif "-r3" in request_id:
            round_num = 3

        payload = {
            "round": round_num,
            "panelist": panelist_config.persona,
            "message": f"[{panelist_config.persona}] round {round_num} analysis",
            "key_takeaway": f"Key insight from round {round_num}",
            "references": [],
            "no_new_arguments": False,
        }
        metrics = {
            "persona": panelist_config.persona,
            "provider": panelist_config.provider,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        return panelist_config, (json.dumps(payload, ensure_ascii=False), metrics)

    def _stub_invoke_sync(self, provider_name, model, system_prompt, user_prompt, request_id, response_format="json"):
        if request_id.endswith("-report"):
            final_report = {
                "executive_summary": "자동화된 테스트 보고서",
                "strongest_consensus": ["테스트 패널이 동일한 결론에 도달했습니다."],
                "remaining_disagreements": [],
                "recommendations": ["지금 바로 출시를 진행하세요."],
            }
            return json.dumps(final_report, ensure_ascii=False), {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            }
        raise AssertionError(f"Unexpected LLM invocation during eager Celery test: {request_id}")

    monkeypatch.setattr(review_tasks.llm_strategy_service, "get_default_panelists", _mock_panelists)
    monkeypatch.setattr(review_tasks, "run_panelist_turn", _stub_run_panelist_turn)
    monkeypatch.setattr(review_tasks.LLMService, "invoke_sync", _stub_invoke_sync, raising=False)

    # --- 1. Create prerequisite rooms ---
    main_room_res = celery_review_client.post("/api/rooms", json={"name": "Main for Celery Test", "type": "main"})
    assert main_room_res.status_code == 200
    main_room_id = main_room_res.json()["room_id"]

    sub_room_res = celery_review_client.post(
        "/api/rooms",
        json={"name": "Sub for Celery Test", "type": "sub", "parent_id": main_room_id}
    )
    assert sub_room_res.status_code == 200
    sub_room_id = sub_room_res.json()["room_id"]

    # --- 2. Create review and ensure Celery chain runs eagerly ---
    review_topic = "Celery Test Topic"
    review_instruction = "Celery test instruction"

    response = celery_review_client.post(
        f"/api/rooms/{sub_room_id}/reviews",
        json={"topic": review_topic, "instruction": review_instruction}
    )
    assert response.status_code == 200
    review_id = response.json()["review_id"]

    # --- 3. Poll until Celery eager chain completes ---
    final_status = None
    for _ in range(15):
        status_res = celery_review_client.get(f"/api/reviews/{review_id}")
        assert status_res.status_code == 200
        final_status = status_res.json()["status"]
        if final_status == "completed":
            break
        await asyncio.sleep(0.2)

    assert final_status == "completed", "Review should complete when Celery runs eagerly"

    # --- 4. Validate final report content ---
    report_res = celery_review_client.get(f"/api/reviews/{review_id}/report")
    assert report_res.status_code == 200
    report_data = report_res.json()["data"]
    assert report_data["topic"] == review_topic
    assert report_data["instruction"] == review_instruction
    assert report_data["executive_summary"] == "자동화된 테스트 보고서"
    assert report_data["recommendations"] == ["지금 바로 출시를 진행하세요."]
