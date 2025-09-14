"""
Celery tasks for generating vector embeddings asynchronously.
"""
import logging
from app.celery_app import celery_app
from app.tasks.base_task import BaseTask
from app.services.llm_service import get_llm_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

from opentelemetry import trace

@celery_app.task(bind=True, base=BaseTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 5})
def generate_embedding_for_record(self: BaseTask, record_id: str, table_name: str, text_content: str):
    """
    Generates an embedding for a given text and saves it to the specified table.

    Args:
        record_id: The primary key of the record to update.
        table_name: The name of the table to update (e.g., 'messages', 'attachment_chunks').
        text_content: The text content to generate the embedding for.
    """
    # Verification for OpenTelemetry: Check if trace context is propagated.
    span = trace.get_current_span()
    span_context = span.get_span_context()
    logger.info(
        f"Celery task received trace context: trace_id={span_context.trace_id}, span_id={span_context.span_id}"
    )

    if not text_content:
        logger.warning(f"Skipping embedding generation for {table_name} {record_id} due to empty content.")
        return

    try:
        logger.info(f"Generating embedding for {table_name} {record_id}...")
        llm_service = get_llm_service()

        # Use the synchronous version of the embedding generation for Celery tasks
        embedding, metrics = llm_service.generate_embedding_sync(text_content)

        # Save the generated embedding to the database
        storage_service.save_embedding(
            table_name=table_name,
            record_id=record_id,
            embedding=embedding
        )

        logger.info(f"Successfully generated and saved embedding for {table_name} {record_id}. Tokens used: {metrics.get('total_tokens', 0)}")
    except Exception as e:
        logger.error(f"Failed to generate embedding for {table_name} {record_id}: {e}", exc_info=True)
        # The task will be retried automatically due to the task decorator settings.
        raise
