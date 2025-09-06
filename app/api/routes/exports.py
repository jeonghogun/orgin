import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.api.dependencies import AUTH_DEPENDENCY
from app.services.conversation_service import ConversationService, get_conversation_service
from app.tasks.export_tasks import create_export

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/threads/{thread_id}/export/jobs", response_model=Dict[str, str], status_code=202)
async def create_export_job(
    thread_id: str,
    format: str = Query("zip", enum=["json", "md", "zip"]),
    user_info: Dict[str, Any] = AUTH_DEPENDENCY,
    convo_service: ConversationService = Depends(get_conversation_service),
):
    user_id = user_info.get("user_id")
    job = convo_service.create_export_job(thread_id, user_id, format)
    create_export.delay(job["id"], thread_id, format)
    return {"jobId": job["id"]}

@router.get("/export/jobs/{job_id}")
async def get_export_job(job_id: str, convo_service: ConversationService = Depends(get_conversation_service)):
    job = convo_service.get_export_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job["status"] == "done" and job["file_url"]:
        # In a real app, this would be a signed URL to cloud storage.
        # Here, it's a local file path, so we can't directly return it.
        # We could serve it via StaticFiles, but that requires configuration.
        # For simplicity, we'll just return the job info.
        return job

    return job

@router.get("/export/jobs/{job_id}/download")
async def download_export(job_id: str, convo_service: ConversationService = Depends(get_conversation_service)):
    job = convo_service.get_export_job(job_id)
    if not job or job["status"] != "done" or not job["file_url"]:
        raise HTTPException(status_code=404, detail="Export not ready or found.")

    # This is a simplification. A real implementation would use Nginx's X-Accel-Redirect
    # or a signed S3 URL to securely serve the file.
    # Redirecting to a static path is not ideal but works for this demo.
    file_path = job["file_url"]
    return RedirectResponse(url=f"/{file_path}")
