"""
Admin-only API endpoints for managing and monitoring the system.
"""
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Body

from app.api.dependencies import require_role, get_admin_service, get_audit_service
from app.services.admin_service import AdminService
from app.services.audit_service import AuditService
from app.tasks.persona_tasks import generate_user_persona
from app.models.schemas import ApiPanelistConfig as PanelistConfig # Assuming this is the right schema for provider config updates

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"]
    # dependencies=[Depends(require_role("admin"))]  # 임시로 주석 처리
)

# --- Dashboard ---
@router.get("/dashboard", response_model=Dict[str, Any])
async def get_dashboard_data(admin_service: AdminService = Depends(get_admin_service)):
    """Get a snapshot of key operational and investor KPIs."""
    kpis = await admin_service.get_dashboard_kpis()
    return kpis

# --- Provider Configuration ---
@router.get("/providers", response_model=List[Dict[str, Any]])
async def get_providers(admin_service: AdminService = Depends(get_admin_service)):
    """Get the current configuration for all LLM providers."""
    return await admin_service.get_provider_configs()

@router.put("/providers/{name}")
async def update_provider(
    name: str,
    config: Dict[str, Any], # A more specific Pydantic model would be better
    # user_info: Dict[str, str] = Depends(require_role("admin")),  # 임시로 주석 처리
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service)
):
    """Update the configuration for a specific provider."""
    await admin_service.update_provider_config(name, config)
    await audit_service.log_action(admin_user_id=user_info['user_id'], action=f"update_provider:{name}", details=config)
    return {"status": "ok", "message": f"Provider '{name}' updated."}

# --- System Settings ---
@router.get("/settings", response_model=Dict[str, Any])
async def get_settings(admin_service: AdminService = Depends(get_admin_service)):
    """Get all configurable system settings."""
    return await admin_service.get_system_settings()

@router.put("/settings")
async def update_settings(
    settings_payload: Dict[str, Any],
    # user_info: Dict[str, str] = Depends(require_role("admin")),  # 임시로 주석 처리
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service)
):
    """Update one or more system settings."""
    for key, value in settings_payload.items():
        await admin_service.update_system_setting(key, value)
    await audit_service.log_action(admin_user_id=user_info['user_id'], action="update_settings", details=settings_payload)
    return {"status": "ok", "message": "Settings updated."}

# --- Persona Management ---
@router.post("/persona/rebuild")
async def rebuild_persona(
    payload: Dict[str, str] = Body(...),
    # user_info: Dict[str, str] = Depends(require_role("admin")),  # 임시로 주석 처리
    audit_service: AuditService = Depends(get_audit_service)
):
    """Trigger a persona generation task for a specific user."""
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required.")

    task = generate_user_persona.delay(user_id)
    await audit_service.log_action(admin_user_id=user_info['user_id'], action="rebuild_persona", details={"user_id": user_id, "task_id": task.id})
    return {"status": "ok", "message": "Persona rebuild task enqueued.", "task_id": task.id}

@router.get("/persona/jobs")
async def get_persona_jobs(limit: int = 50):
    """Get the status of recent persona generation jobs."""
    # This requires inspecting the Celery backend, which is complex.
    # Returning a placeholder for now.
    return {"status": "ok", "jobs": []}

# --- Fact Management ---
from app.services.user_fact_service import UserFactService
from app.api.dependencies import get_user_fact_service

@router.get("/facts/pending-review", response_model=List[Dict[str, Any]])
async def get_facts_pending_review(
    limit: int = 50,
    offset: int = 0,
    user_fact_service: UserFactService = Depends(get_user_fact_service),
):
    """Get a list of user facts that are pending manual review."""
    facts = await user_fact_service.get_facts_pending_review(limit=limit, offset=offset)
    return facts

@router.post("/facts/resolve-conflict")
async def resolve_fact_conflict(
    payload: Dict[str, str] = Body(...),
    # user_info: Dict[str, str] = Depends(require_role("admin")),
    user_fact_service: UserFactService = Depends(get_user_fact_service),
    audit_service: AuditService = Depends(get_audit_service)
):
    """Resolve a fact conflict by choosing a winner and a loser."""
    winning_fact_id = payload.get("winning_fact_id")
    losing_fact_id = payload.get("losing_fact_id")

    if not winning_fact_id or not losing_fact_id:
        raise HTTPException(status_code=400, detail="winning_fact_id and losing_fact_id are required.")

    await user_fact_service.resolve_fact_conflict(winning_fact_id, losing_fact_id)
    
    # await audit_service.log_action(admin_user_id=user_info['user_id'], action="resolve_fact_conflict", details=payload)
    
    return {"status": "ok", "message": "Conflict resolved successfully."}