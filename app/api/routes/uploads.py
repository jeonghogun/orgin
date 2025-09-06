import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from app.models.conversation_schemas import Attachment
from app.services.conversation_service import ConversationService, get_conversation_service
from app.tasks.attachment_tasks import process_attachment

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

    file_location = UPLOAD_DIR / file.filename
    try:
        with file_location.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    attachment_data = {
        "kind": "file",
        "name": file.filename,
        "mime": file.content_type or "application/octet-stream",
        "size": file_location.stat().st_size,
        "url": str(file_location),
    }

    try:
        created_attachment = convo_service.create_attachment(attachment_data)
        process_attachment.delay(created_attachment.id)
        return created_attachment
    except Exception as e:
        logger.error(f"Failed to create attachment record for {file.filename}: {e}", exc_info=True)
        file_location.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save file metadata.")
