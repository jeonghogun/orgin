import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

from app.models.conversation_schemas import Attachment
from app.services.conversation_service import ConversationService, get_conversation_service
from app.tasks.attachment_tasks import process_attachment
from app.services.cloud_storage_service import get_cloud_storage_service
from app.services.file_validation_service import (
    FileValidationError,
    get_file_validation_service,
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/uploads", response_model=List[Attachment], status_code=200)
async def upload_file(
    files: Optional[List[UploadFile]] = File(default=None),
    file: Optional[UploadFile] = File(default=None),
    thread_id: Optional[str] = Form(None),
    convo_service: ConversationService = Depends(get_conversation_service),
):
    uploads: List[UploadFile] = []
    if file is not None:
        uploads.append(file)
    if files:
        uploads.extend(files)

    if not uploads:
        raise HTTPException(status_code=400, detail="No files provided.")

    validation_service = get_file_validation_service()
    cloud_storage = get_cloud_storage_service()
    created_attachments: List[Attachment] = []

    for upload in uploads:
        if not upload.filename:
            raise HTTPException(status_code=400, detail="No file name provided.")

        try:
            validation_service.ensure_extension_allowed(upload.filename)
            unique_name = validation_service.generate_unique_name(upload.filename)
        except FileValidationError as validation_error:
            raise HTTPException(status_code=validation_error.status_code, detail=str(validation_error)) from validation_error

        temp_path = validation_service.temp_path_for(unique_name)
        try:
            validation_service.write_upload_to_temp(upload, temp_path)
            validation_service.scan_file(temp_path)
            file_location = validation_service.promote_to_permanent_storage(temp_path, unique_name)
        except FileValidationError as validation_error:
            logger.warning("Upload rejected for %s: %s", upload.filename, validation_error)
            temp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=validation_error.status_code, detail=str(validation_error)) from validation_error
        except Exception as unexpected_error:
            logger.error("Unexpected failure while storing upload %s", upload.filename, exc_info=True)
            temp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Failed to persist uploaded file.") from unexpected_error
        finally:
            try:
                upload.file.close()
            except Exception:
                logger.debug("Upload file stream already closed for %s", upload.filename)

        storage_uri = None
        if cloud_storage.is_configured():
            storage_uri = cloud_storage.upload_file(file_location, f"attachments/{unique_name}")
            if storage_uri:
                logger.info("Stored attachment %s in Cloud Storage", storage_uri)

        attachment_payload = {
            "kind": "file",
            "name": upload.filename,
            "mime": upload.content_type or "application/octet-stream",
            "size": file_location.stat().st_size,
            "url": storage_uri or str(file_location),
        }

        try:
            attachment = convo_service.create_attachment(attachment_payload, thread_id=thread_id)
            try:
                process_attachment.delay(attachment.id)
            except Exception as task_error:
                logger.warning("Failed to enqueue attachment processing for %s: %s", attachment.id, task_error)

            if storage_uri:
                signed_url = cloud_storage.generate_signed_url(storage_uri)
                if signed_url:
                    attachment = attachment.model_copy(update={"url": signed_url})
            created_attachments.append(attachment)
        except Exception as db_error:
            logger.error(
                "Failed to create attachment record for %s: %s",
                upload.filename,
                db_error,
                exc_info=True,
            )
            file_location.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Could not save file metadata.")

    return created_attachments
