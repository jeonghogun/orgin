"""
Celery tasks for persona generation.
"""
import logging
import json
from asgiref.sync import async_to_sync
from app.celery_app import celery_app
from app.services.storage_service import StorageService
from app.services.memory_service import MemoryService
from app.services.llm_service import LLMService
from app.utils.trace_id import trace_id_var

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def generate_user_persona(self, user_id: str):
    """
    Analyzes a user's message history in their 'main' room to generate and
    update their persona profile.
    """
    # Set a trace_id for logging and tracking
    trace_id = self.request.id or "persona-gen-" + user_id
    trace_id_var.set(trace_id)
    logger.info(f"Starting persona generation for user_id: {user_id} with trace_id: {trace_id}")

    # Use async_to_sync to call async functions from this sync Celery task
    async_to_sync(persona_generation_logic)(user_id, trace_id)


async def persona_generation_logic(user_id: str, trace_id: str):
    """
    The core async logic for generating a user persona.
    """
    storage_service = StorageService()
    memory_service = MemoryService()
    llm_service = LLMService()

    try:
        # 1. Find the user's main room
        user_rooms = await storage_service.get_rooms_by_owner(user_id)
        main_room = next((room for room in user_rooms if room.type == "main"), None)

        if not main_room:
            logger.warning(f"No main room found for user {user_id}. Cannot generate persona.")
            return

        # 2. Get message history from the main room
        messages = await storage_service.get_messages(main_room.room_id)

        # We need a certain amount of history to create a meaningful persona
        if len(messages) < 10:
            logger.info(f"Not enough message history for user {user_id} to generate persona (found {len(messages)} messages).")
            return

        # 3. Format message history for the LLM
        message_history = "\n".join(
            [f"{msg.role}: {msg.content}" for msg in messages if msg.role == 'user']
        )

        # Limit history size to avoid excessive token usage
        max_history_length = 10000 # Approx 2500 tokens
        if len(message_history) > max_history_length:
            message_history = message_history[-max_history_length:]


        # 4. Call LLM to generate the persona summary
        logger.info(f"Generating persona summary for user {user_id} from {len(messages)} messages.")
        persona_json_str, _ = await llm_service.generate_persona_summary(
            message_history=message_history,
            request_id=trace_id
        )

        # 5. Parse the response and update the user's profile
        try:
            persona_data = json.loads(persona_json_str)
            logger.info(f"Generated persona data for user {user_id}: {persona_data}")

            # Ensure we only update fields that are part of the persona generation
            update_payload = {
                "conversation_style": persona_data.get("conversation_style"),
                "interests": persona_data.get("interests", [])
            }
            # Filter out any None values so we don't overwrite existing fields with null
            update_payload = {k: v for k, v in update_payload.items() if v is not None}

            if update_payload:
                await memory_service.update_user_profile(user_id, update_payload)
            else:
                logger.warning(f"Persona generation for user {user_id} resulted in empty payload.")

        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from LLM response for user {user_id}: {persona_json_str}")
        except Exception as e:
            logger.error(f"Failed to parse and save persona for user {user_id}: {e}")

    except Exception as e:
        logger.error(f"An unexpected error occurred during persona generation for user {user_id}: {e}", exc_info=True)
