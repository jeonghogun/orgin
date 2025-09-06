import logging
import asyncio
from PyPDF2 import PdfReader
from pathlib import Path

from app.celery_app import celery_app
from app.services.rag_service import get_rag_service
from app.services.conversation_service import get_conversation_service

logger = logging.getLogger(__name__)

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100):
    start = 0
    while start < len(text):
        end = start + chunk_size
        yield text[start:end]
        start += chunk_size - overlap

@celery_app.task(name="tasks.process_attachment")
def process_attachment(attachment_id: str):
    logger.info(f"Starting RAG processing for attachment: {attachment_id}")
    convo_service = get_conversation_service()
    rag_service = get_rag_service()

    attachment = convo_service.get_attachment_by_id(attachment_id)
    if not attachment:
        logger.error(f"Attachment {attachment_id} not found.")
        return

    file_path = Path(attachment["url"])
    if not file_path.exists():
        logger.error(f"File for attachment {attachment_id} not found at {file_path}")
        return

    text_content = ""
    if attachment["mime"] == "application/pdf":
        try:
            reader = PdfReader(str(file_path))
            for page in reader.pages:
                text_content += page.extract_text() or ""
        except Exception as e:
            logger.error(f"Failed to extract text from PDF {file_path}: {e}")
            return
    else:
        logger.warning(f"Unsupported MIME type for extraction: {attachment['mime']}")
        return

    if not text_content.strip():
        logger.warning(f"No text content extracted from {file_path}")
        return

    text_chunks = list(chunk_text(text_content))

    try:
        asyncio.run(rag_service.create_and_store_chunks(attachment_id, text_chunks))
    except Exception as e:
        logger.error(f"Async call to create_and_store_chunks failed: {e}")
        return

    logger.info(f"Finished RAG processing for attachment: {attachment_id}")
    return {"attachment_id": attachment_id, "status": "complete"}
