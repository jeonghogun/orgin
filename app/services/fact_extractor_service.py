import logging
import re
import json
from typing import Dict, Any, Optional

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
        self._name_patterns = [
            re.compile(r"(?:내|제|저의)\s*이름(?:은|은요|은지)?\s*([\w가-힣]+)", re.IGNORECASE),
            re.compile(r"(?:나를|저를)\s*([\w가-힣]+)\s*라고\s*불러", re.IGNORECASE),
            re.compile(r"(?:이름은)\s*([\w가-힣]+)", re.IGNORECASE),
        ]
        self._name_suffixes = ("입니다", "이에요", "예요", "이야", "야", "라고", "라고요", "라고해")

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
                facts = []

        except Exception as e:
            logger.error(f"Failed to extract facts using LLM for message {message_id}: {e}", exc_info=True)
            facts = []

        fallback_facts = self._extract_with_patterns(message_content)

        if not facts and fallback_facts:
            logger.info(
                "Fallback fact extraction succeeded for message %s with patterns: %s",
                message_id,
                [fact.get("type") for fact in fallback_facts],
            )
            return fallback_facts

        if facts and fallback_facts:
            existing_types = {fact.get("type") for fact in facts}
            for fallback in fallback_facts:
                if fallback.get("type") not in existing_types:
                    facts.append(fallback)

        return facts

    def _clean_name(self, raw_name: str) -> Optional[str]:
        if not raw_name:
            return None
        name = raw_name.strip()
        name = re.sub(r"[\s,.;!?]+$", "", name)
        for suffix in self._name_suffixes:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        name = name.strip()
        if any(char.isdigit() for char in name):
            return None
        if len(name) < 2 or len(name) > 10:
            return None
        return name

    def _extract_with_patterns(self, message_content: str) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        if not message_content:
            return extracted

        if "이름" not in message_content and "불러" not in message_content:
            return extracted

        for pattern in self._name_patterns:
            match = pattern.search(message_content)
            if match:
                candidate = self._clean_name(match.group(1))
                if candidate:
                    extracted.append(
                        {
                            "type": FactType.USER_NAME.value,
                            "value": candidate,
                            "confidence": 0.6,
                        }
                    )
                    break
        return extracted
