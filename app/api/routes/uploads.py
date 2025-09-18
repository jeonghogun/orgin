import logging
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from app.models.conversation_schemas import Attachment
from app.services.conversation_service import ConversationService, get_conversation_service
from app.tasks.attachment_tasks import process_attachment
from app.services.cloud_storage_service import get_cloud_storage_service

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/uploads", response_model=Attachment, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    convo_service: ConversationService = Depends(get_conversation_service),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided.")

    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_location = UPLOAD_DIR / unique_name
    try:
        with file_location.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    cloud_storage = get_cloud_storage_service()
    storage_uri = None
    if cloud_storage.is_configured():
        storage_uri = cloud_storage.upload_file(file_location, f"attachments/{unique_name}")
        if storage_uri:
            logger.info("Stored attachment %s in Cloud Storage", storage_uri)

    attachment_data = {
        "kind": "file",
        "name": file.filename,
        "mime": file.content_type or "application/octet-stream",
        "size": file_location.stat().st_size,
        "url": storage_uri or str(file_location),
    }

    try:
        created_attachment = convo_service.create_attachment(attachment_data)
        process_attachment.delay(created_attachment.id)

        # For client consumption, prefer a signed URL when the file lives in Cloud Storage.
        if storage_uri:
            signed_url = cloud_storage.generate_signed_url(storage_uri)
            if signed_url:
                return created_attachment.model_copy(update={"url": signed_url})
        return created_attachment
    except Exception as e:
        logger.error(f"Failed to create attachment record for {file.filename}: {e}", exc_info=True)
        file_location.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save file metadata.")
