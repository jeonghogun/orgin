"""
Intent Service - LLM-based intent classification and entity extraction
"""
import json
import logging
from typing import Dict, Any, Optional
from app.services.llm_service import llm_service
from app.config.settings import settings

logger = logging.getLogger(__name__)


class IntentService:
    """LLM-based intent classification and entity extraction service"""
    
    def __init__(self):
        self.llm_provider = llm_service.get_provider()
    
    async def classify_intent(self, message: str, request_id: str = None) -> Dict[str, Any]:
        """
        Classify user intent and extract entities using LLM
        
        Returns:
            Dict with intent, entities, and confidence
        """
        try:
            prompt = f"""
사용자 메시지의 의도를 분류하고 필요한 정보를 추출하세요.

메시지: "{message}"

다음 JSON 형식으로만 응답하세요:
{{
    "intent": "time|weather|search|wiki|name_set|name_get|general",
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
- general: 위에 해당하지 않는 모든 일반적인 대화

중요: 메시지에 시간 관련 단어가 있으면 반드시 "time"으로 분류하세요.
"""

            response = await self.llm_provider.invoke(
                model=settings.LLM_MODEL,
                system_prompt="당신은 의도 분류 전문가입니다. 사용자 메시지를 분석하여 정확한 JSON만 응답하세요. 다른 텍스트나 설명은 절대 포함하지 마세요.",
                user_prompt=prompt,
                request_id=request_id or "intent_classification",
                response_format="json"
            )
            
            # Parse JSON response
            result = json.loads(response["content"])
            
            # Validate result structure
            if not isinstance(result, dict):
                raise ValueError("Invalid response format")
            
            if "intent" not in result:
                raise ValueError("Missing intent in response")
            
            # Ensure entities exist
            if "entities" not in result:
                result["entities"] = {}
            
            # Set default confidence if missing
            if "confidence" not in result:
                result["confidence"] = 0.9
            
            logger.info(f"Intent classified: {result['intent']} (confidence: {result['confidence']})")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Fallback to general intent
            return {
                "intent": "general",
                "entities": {},
                "confidence": 0.5
            }
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            # Fallback to general intent
            return {
                "intent": "general",
                "entities": {},
                "confidence": 0.3
            }
    
    def _extract_location_from_text(self, text: str) -> Optional[str]:
        """Extract location from text using simple pattern matching"""
        locations = ["서울", "부산", "해운대", "제주", "강남", "홍대", "신촌", "명동", "동대문"]
        text_lower = text.lower()
        
        for location in locations:
            if location in text_lower:
                return location
        
        return None


# Global instance
intent_service = IntentService()
