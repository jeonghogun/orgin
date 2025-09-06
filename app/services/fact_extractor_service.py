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
            # MBTI-A, MBTI-T와 같은 변형을 처리하기 위해 4자로 제한
            if len(value) > 4:
                value = value[:4]

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
        다음 사용자 메시지를 분석하여 사용자에 대한 정보를 추출하세요.
        사용자 메시지: "{message_content}"

        다음 유형의 사실이 있다면 추출하세요: {', '.join([ft.value for ft in FactType])}.
        JSON 객체로 응답하되, "facts" 키 하나만 포함하세요. 이 키의 값은 사실 객체들의 배열이어야 합니다.
        각 사실 객체는 "type", "value", "confidence" (0.0-1.0 사이의 실수) 세 개의 키를 가져야 합니다.
        사실이 없다면 빈 배열을 반환하세요.
        
        특히 "내 이름은 XXX야" 같은 패턴에서 사용자 이름을 추출하세요.
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
