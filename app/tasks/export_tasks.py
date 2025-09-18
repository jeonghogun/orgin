import logging
import io
import zipfile
from pathlib import Path
from typing import List

from app.celery_app import celery_app
from app.services.conversation_service import get_conversation_service
from app.services.cloud_storage_service import get_cloud_storage_service

logger = logging.getLogger(__name__)

# This service would need to be updated to manage job statuses
# For now, we'll just log things.
# A real implementation would have an ExportJobService.

@celery_app.task(name="tasks.create_export")
def create_export(job_id: str, thread_id: str, format: str):
    logger.info(f"Starting export job {job_id} for thread {thread_id} in format {format}")
    convo_service = get_conversation_service()

    cloud_storage = get_cloud_storage_service()
    temp_files: List[Path] = []

    try:
        messages = convo_service.get_all_messages_by_thread(thread_id)
        if not messages:
            raise ValueError("Thread has no messages.")

        export_dir = Path("uploads/exports")
        export_dir.mkdir(exist_ok=True)
        file_path = export_dir / f"{job_id}.{format}"

        if format == "zip":
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                md_content = f"# Thread: {thread_id}\n\n" + "\n\n---\n\n".join([f"**{msg['role'].title()}**:\n\n{msg['content']}" for msg in messages])
                zip_file.writestr(f"conversation_{thread_id}.md", md_content)

                attachment_ids = set()
                for msg in messages:
                    if msg.get("meta") and msg["meta"].get("attachments"):
                        for att_id in msg["meta"]["attachments"]:
                            attachment_ids.add(att_id)

                for att_id in attachment_ids:
                    attachment = convo_service.get_attachment_by_id(att_id)
                    if not attachment:
                        continue
                    try:
                        local_path = cloud_storage.ensure_local_copy(attachment["url"])
                    except FileNotFoundError as exc:
                        logger.warning("Attachment %s could not be included in export: %s", att_id, exc)
                        continue

                    try:
                        arcname = f"attachments/{Path(local_path).name}"
                        zip_file.write(local_path, arcname=arcname)
                    finally:
                        if local_path != Path(attachment["url"]):
                            temp_files.append(local_path)

            with open(file_path, "wb") as f:
                f.write(zip_buffer.getvalue())
        else:
            if format == "json":
                import json
                content = json.dumps(messages, indent=2)
            else:  # md
                content = f"# Thread: {thread_id}\n\n" + "\n\n---\n\n".join([f"**{msg['role'].title()}**:\n\n{msg['content']}" for msg in messages])

            file_path.write_text(content, encoding="utf-8")

        storage_uri = None
        if cloud_storage.is_configured():
            storage_uri = cloud_storage.upload_file(file_path, f"exports/{file_path.name}")
            if storage_uri:
                logger.info("Uploaded export %s to Cloud Storage", storage_uri)
                file_url = storage_uri
                # remove local copy after successful upload
                file_path.unlink(missing_ok=True)
            else:
                file_url = str(file_path)
        else:
            file_url = str(file_path)

        convo_service.update_export_job_status(job_id, "done", file_url=file_url)
        logger.info(f"Export job {job_id} completed. File at: {file_url}")

    except Exception as e:
        error_message = str(e)
        logger.error(f"Export job {job_id} failed: {error_message}", exc_info=True)
        convo_service.update_export_job_status(job_id, "error", error_message=error_message)

    finally:
        for temp in temp_files:
            temp.unlink(missing_ok=True)

    return {"job_id": job_id, "status": "complete"}
