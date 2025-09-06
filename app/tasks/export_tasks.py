import logging
import time
import io
import zipfile
from pathlib import Path

from app.celery_app import celery_app
from app.services.conversation_service import get_conversation_service

logger = logging.getLogger(__name__)

# This service would need to be updated to manage job statuses
# For now, we'll just log things.
# A real implementation would have an ExportJobService.

@celery_app.task(name="tasks.create_export")
def create_export(job_id: str, thread_id: str, format: str):
    logger.info(f"Starting export job {job_id} for thread {thread_id} in format {format}")
    convo_service = get_conversation_service()

    try:
        messages = convo_service.get_all_messages_by_thread(thread_id)
        if not messages:
            raise ValueError("Thread has no messages.")

        # In a real app, this would save to a cloud storage (e.g., S3)
        # and the URL would be a signed URL to that object.
        # For now, we save to the local 'uploads' directory.
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
                    if attachment and Path(attachment["url"]).exists():
                        zip_file.write(attachment["url"], arcname=f"attachments/{Path(attachment['url']).name}")

            with open(file_path, "wb") as f:
                f.write(zip_buffer.getvalue())
        else:
            # Handle md/json
            content = ""
            if format == "json":
                import json
                content = json.dumps(messages, indent=2)
            else: # md
                content = f"# Thread: {thread_id}\n\n" + "\n\n---\n\n".join([f"**{msg['role'].title()}**:\n\n{msg['content']}" for msg in messages])

            file_path.write_text(content, encoding='utf-8')

        convo_service.update_export_job_status(job_id, "done", file_url=str(file_path))
        logger.info(f"Export job {job_id} completed. File at: {file_path}")

    except Exception as e:
        error_message = str(e)
        logger.error(f"Export job {job_id} failed: {error_message}", exc_info=True)
        convo_service.update_export_job_status(job_id, "error", error_message=error_message)

    return {"job_id": job_id, "status": "complete"}
