"""
Intent Service - LLM-based intent classification and entity extraction
"""

import json
import logging
import re
from typing import Dict, Any, Optional, TypedDict, cast, List
from app.services.llm_service import LLMService
from app.config.settings import settings

logger = logging.getLogger(__name__)


class IntentResult(TypedDict):
    intent: str
    entities: Dict[str, Any]
    confidence: float


class IntentService:
    """LLM-based intent classification and entity extraction service"""

    TIME_KEYWORDS = [
        "몇 시", "몇시", "지금 시간", "현재 시간", "현재시간", "시간 알려", "시간좀",
        "몇시야", "몇시에", "몇시인지", "오늘 시간", "시간이 몇"
    ]
    DATE_KEYWORDS = [
        "날짜", "며칠", "몇일", "오늘 몇", "오늘 날짜", "오늘은 몇",
        "오늘 며칠", "오늘 몇 일이", "오늘 몇 일이야"
    ]
    WEATHER_KEYWORDS = [
        "날씨", "기온", "온도", "비와", "비 와", "비가", "비 올", "눈 와",
        "날씨 어때", "날씨 알려", "날씨 좀", "기상", "습도"
    ]
    NAME_GET_KEYWORDS = [
        "내 이름", "제 이름", "내이름", "제이름", "내 이름이 뭐", "이름이 뭐야",
        "내 이름 뭐", "내가 누구야", "내가 누구", "내 이름 기억", "이름 기억해"
    ]
    NAME_SET_PATTERNS = [
        re.compile(r"(?:내|제|저의)\s*이름(?:은|은요|은지)?\s*([\w가-힣]+)", re.IGNORECASE),
        re.compile(r"(?:나를|저를)\s*([\w가-힣]+)\s*라고\s*불러", re.IGNORECASE),
        re.compile(r"(?:이름은)\s*([\w가-힣]+)", re.IGNORECASE),
    ]
    NAME_SUFFIXES = ("입니다", "이에요", "예요", "이야", "야", "라고", "라고요", "라고해")
    SMALLTALK_KEYWORDS = [
        "안녕",
        "안녕하세요",
        "하이",
        "hello",
        "hi",
        "고마워",
        "감사",
        "반가워",
        "잘 있어",
        "수고",
    ]

    def __init__(self, llm_service: LLMService):
        super().__init__()
        self.llm_service = llm_service
        self.llm_provider = None

    def _contains_keyword(self, text: str, keywords: List[str]) -> bool:
        if not text:
            return False
        compressed = text.replace(" ", "")
        return any(keyword in text or keyword in compressed for keyword in keywords)

    def _clean_name(self, raw_name: str) -> Optional[str]:
        if not raw_name:
            return None
        name = raw_name.strip()
        # Remove trailing punctuation and descriptive suffixes
        name = re.sub(r"[\s,.;!?]+$", "", name)
        for suffix in self.NAME_SUFFIXES:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        name = name.strip()
        if not name:
            return None
        # Filter out overly long or alphanumeric strings to avoid false positives
        if any(char.isdigit() for char in name):
            return None
        if len(name) > 10:
            return None
        return name

    def _detect_name_set(self, message: str) -> Optional[str]:
        if "이름" not in message and "불러" not in message:
            return None
        for pattern in self.NAME_SET_PATTERNS:
            match = pattern.search(message)
            if match:
                candidate = self._clean_name(match.group(1))
                if candidate and len(candidate) >= 2:
                    return candidate
        return None

    def _classify_with_rules(self, message: str) -> Optional[IntentResult]:
        if not message:
            return None
        lowered = message.lower()

        detected_name = self._detect_name_set(message)
        if detected_name:
            return IntentResult(
                intent="name_set",
                entities={"name": detected_name},
                confidence=0.96,
            )

        if self._contains_keyword(lowered, self.NAME_GET_KEYWORDS):
            return IntentResult(intent="name_get", entities={}, confidence=0.95)

        if self._contains_keyword(lowered, self.TIME_KEYWORDS) or self._contains_keyword(
            lowered, self.DATE_KEYWORDS
        ):
            return IntentResult(intent="time", entities={}, confidence=0.93)

        if self._contains_keyword(lowered, self.WEATHER_KEYWORDS):
            location = self._extract_location_from_text(lowered)
            entities: Dict[str, Any] = {}
            if location:
                entities["location"] = location
            return IntentResult(intent="weather", entities=entities, confidence=0.9)

        if self._is_smalltalk(message, lowered):
            return IntentResult(intent="general", entities={}, confidence=0.6)

        return None

    async def classify_intent(
        self, message: str, request_id: Optional[str] = None
    ) -> IntentResult:
        """
        Classify user intent and extract entities using LLM

        Returns:
            Dict with intent, entities, and confidence
        """
        rule_based = self._classify_with_rules(message)
        if rule_based:
            logger.info(
                "Intent matched by heuristic rules: %s (confidence: %s)",
                rule_based["intent"],
                rule_based["confidence"],
            )
            return rule_based

        try:
            prompt = f"""
사용자 메시지의 의도를 분류하고 필요한 정보를 추출하세요.

메시지: "{message}"

다음 JSON 형식으로만 응답하세요:
{{
    "intent": "time|weather|search|wiki|name_set|name_get|review|general",
    "entities": {{
        "location": "지역명 (날씨용, 없으면 null)",
        "name": "이름 (이름 저장/조회용, 없으면 null)",
        "query": "검색어 (검색용, 없으면 null)",
        "topic": "위키 주제 (위키용, 없으면 null)"
    }},
    "confidence": 0.95
}}

의도 분류 기준:
- time: 시간, 시계, 몇시, 현재시간, 지금시간 등이 포함된 질문
- weather: 날씨, 기온, 온도, 비, 맑음, 흐림 등이 포함된 질문
- search: 검색, 찾아줘, 알려줘, 구글 등이 포함된 요청
- wiki: 위키, wikipedia, 위키피디아 등이 포함된 요청
- name_set: "내 이름은", "저를 ...라고 불러", "이름이 ...야" 등 이름 저장
- name_get: "내 이름", "내이름", "내가 누구야" 등 이름 조회
- review: "검토", "리뷰", "분석", "토론" 등이 포함된 검토 요청
- general: 위에 해당하지 않는 모든 일반적인 대화

중요: 메시지에 시간 관련 단어가 있으면 반드시 "time"으로 분류하세요.
"""
            if not self.llm_provider:
                self.llm_provider = self.llm_service.get_provider()

            content, _ = await self.llm_provider.invoke(
                model=settings.LLM_MODEL,
                system_prompt="당신은 의도 분류 전문가입니다. 사용자 메시지를 분석하여 정확한 JSON만 응답하세요. 다른 텍스트나 설명은 절대 포함하지 마세요.",
                user_prompt=prompt,
                request_id=request_id or "intent_classification",
                response_format="json",
            )

            # Parse JSON response
            result = cast(Dict[str, Any], json.loads(content))

            if "intent" not in result:
                raise ValueError("Missing intent in response")

            # Ensure entities exist
            if "entities" not in result or not isinstance(result["entities"], dict):
                result["entities"] = {}

            # Set default confidence if missing
            if "confidence" not in result or not isinstance(result["confidence"], (int, float)):
                result["confidence"] = 0.9

            logger.info(
                f"Intent classified: {result['intent']} (confidence: {result['confidence']})"
            )
            return IntentResult(
                intent=str(result["intent"]),
                entities=cast(Dict[str, Any], result["entities"]),
                confidence=float(result["confidence"]),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Fallback to general intent
            return IntentResult(intent="general", entities={}, confidence=0.5)
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            if rule_based:
                return rule_based
            return IntentResult(intent="general", entities={}, confidence=0.3)

    def _is_smalltalk(self, original: str, lowered: str) -> bool:
        stripped = original.strip()
        if not stripped:
            return False

        if any(keyword in lowered for keyword in self.SMALLTALK_KEYWORDS):
            return True

        if len(stripped) <= 8 and not any(char in stripped for char in "?!"):
            keyword_groups = (
                self.TIME_KEYWORDS
                + self.DATE_KEYWORDS
                + self.WEATHER_KEYWORDS
                + self.NAME_GET_KEYWORDS
            )
            if not any(keyword in lowered for keyword in keyword_groups):
                return True

        return False

    def _extract_location_from_text(self, text: str) -> Optional[str]:
        """Extract location from text using simple pattern matching"""
        locations = [
            "서울",
            "부산",
            "해운대",
            "제주",
            "강남",
            "홍대",
            "신촌",
            "명동",
            "동대문",
        ]
        text_lower = text.lower()

        for location in locations:
            if location in text_lower:
                return location

        return None
