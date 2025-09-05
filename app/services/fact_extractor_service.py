import logging
import re
import json
from typing import Dict, Any

from app.services.llm_service import LLMService
from app.services.fact_types import FactType, FactSensitivity

logger = logging.getLogger(__name__)

class FactExtractorService:
    """
    This service is responsible for two main tasks:
    1. Extracting raw facts from a user message using an LLM.
    2. Normalizing the values of extracted facts for consistent storage.
    """

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        self.korean_consonants_and_vowels = "([ㄱ-ㅎㅏ-ㅣ])"

    def normalize_value(self, fact_type: FactType, value: str) -> str:
        """
        Normalizes a fact's value based on its type.
        """
        value = value.lower().strip()
        value = re.sub(r'[^a-z0-9\s\uac00-\ud7a3]', '', value)
        value = re.sub(self.korean_consonants_and_vowels, "", value)
        value = re.sub(r'\s+', ' ', value).strip()

        if fact_type == FactType.MBTI:
            value = value.upper()

        return value

    def get_sensitivity(self, fact_type: FactType) -> FactSensitivity:
        """Maps a fact type to its default sensitivity level."""
        mapping = {
            FactType.USER_NAME: FactSensitivity.PRIVATE,
            FactType.JOB: FactSensitivity.PUBLIC,
            FactType.HOBBY: FactSensitivity.PUBLIC,
            FactType.MBTI: FactSensitivity.PUBLIC,
            FactType.GOAL: FactSensitivity.PRIVATE,
        }
        return mapping.get(fact_type, FactSensitivity.LOW)

    async def extract_facts_from_message(self, message_content: str, message_id: str) -> list[dict[str, Any]]:
        """
        Uses an LLM to extract potential facts from a user's message.
        """
        prompt = f"""
        Analyze the following user message and extract any facts that reveal information about the user.
        The user's message is: "{message_content}"

        Extract facts for the following types if they are present: {', '.join([ft.value for ft in FactType])}.
        Respond with a JSON object containing a single key "facts", which is a list of fact objects.
        Each fact object should have three keys: "type", "value", and "confidence" (a float between 0.0 and 1.0).
        If no facts are found, return an empty list.
        """
        try:
            provider = self.llm_service.get_provider()
            response_content, _ = await provider.invoke(
                model="gpt-4o-mini",
                system_prompt="You are an expert at structured data extraction.",
                user_prompt=prompt,
                request_id=f"fact_extraction_{message_id}",
                response_format="json"
            )

            result = json.loads(response_content)
            facts = result.get("facts", [])
            if not isinstance(facts, list):
                logger.warning(f"LLM returned non-list for facts: {facts}")
                return []

            return facts
        except Exception as e:
            logger.error(f"Failed to extract facts using LLM for message {message_id}: {e}", exc_info=True)
            return []
