import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.api.dependencies import AUTH_DEPENDENCY
from app.services.conversation_service import ConversationService, get_conversation_service
from app.tasks.export_tasks import create_export
from app.services.cloud_storage_service import get_cloud_storage_service

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
        cloud_storage = get_cloud_storage_service()
        signed_url = cloud_storage.generate_signed_url(job["file_url"])
        if signed_url:
            job = {**job, "download_url": signed_url}
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
    cloud_storage = get_cloud_storage_service()
    signed_url = cloud_storage.generate_signed_url(file_path)
    if signed_url:
        return RedirectResponse(url=signed_url)

    return RedirectResponse(url=f"/{file_path}")
