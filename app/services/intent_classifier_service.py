"""
Intent Classification Service
LLM 기반 의도 분류를 통한 검색 필요성 및 사실 질문 감지
"""
import logging
import json
from typing import Dict, Any, Optional, List
from enum import Enum

from app.services.llm_service import LLMService
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

class IntentType(Enum):
    SEARCH_NEEDED = "search_needed"
    FACT_QUERY = "fact_query"
    GENERAL_CHAT = "general_chat"
    UNKNOWN = "unknown"

class FactQueryType(Enum):
    USER_NAME = "user_name"
    JOB = "job"
    HOBBY = "hobby"
    MBTI = "mbti"
    GOAL = "goal"
    NONE = "none"

class IntentClassificationResult:
    def __init__(self, intent_type: IntentType, confidence: float, fact_type: Optional[FactQueryType] = None, reasoning: str = ""):
        self.intent_type = intent_type
        self.confidence = confidence
        self.fact_type = fact_type
        self.reasoning = reasoning

class IntentClassifierService:
    """LLM 기반 의도 분류 서비스"""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        # Fallback 키워드들
        self.search_keywords = [
            "검색", "찾아", "알려줘", "출시일", "날씨", "뉴스", "최신", 
            "언제", "어디", "누구", "무엇", "어떻게", "왜", 
            "gpt", "claude", "gemini", "탄핵", "정치", "경제", 
            "스포츠", "연예", "기술", "과학", "코로나", "경기", "주식"
        ]
        self.fact_keywords = {
            FactQueryType.USER_NAME: ["내 이름", "제 이름", "이름이 뭐", "이름은", "내이름", "제이름"],
            FactQueryType.JOB: ["내 직업", "제 직업", "직업이 뭐", "직업은", "내직업", "제직업"],
            FactQueryType.HOBBY: ["내 취미", "제 취미", "취미가 뭐", "취미는", "내취미", "제취미"],
            FactQueryType.MBTI: ["내 mbti", "제 mbti", "mbti가 뭐", "mbti는", "내mbti", "제mbti"],
            FactQueryType.GOAL: ["내 목표", "제 목표", "목표가 뭐", "목표는", "내목표", "제목표"]
        }

    async def classify_intent(self, user_message: str) -> IntentClassificationResult:
        """
        사용자 메시지의 의도를 분류합니다.
        LLM 기반 분류를 시도하고, 실패 시 키워드 기반 fallback을 사용합니다.
        """
        try:
            # LLM 기반 분류 시도
            result = await self._classify_with_llm(user_message)
            if result.confidence > 0.7:  # 높은 신뢰도면 LLM 결과 사용
                logger.info(f"LLM classification successful: {result.intent_type.value} (confidence: {result.confidence})")
                return result
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}, falling back to keyword matching")
        
        # Fallback: 키워드 기반 분류
        return self._classify_with_keywords(user_message)

    async def _classify_with_llm(self, user_message: str) -> IntentClassificationResult:
        """LLM을 사용한 의도 분류"""
        prompt = f"""
다음 사용자 메시지를 분석하여 의도를 분류하세요.

사용자 메시지: "{user_message}"

분류 기준:
1. search_needed: 최신 정보, 사실 확인, 검색이 필요한 질문
   - "언제", "어디", "누구", "무엇", "어떻게", "왜" 등의 질문
   - 특정 인물, 사건, 날짜, 장소에 대한 정보 요청
   - "검색해서 알려줘", "찾아서 알려줘" 등의 명시적 검색 요청
   - 뉴스, 날씨, 주식, 기술 동향 등 실시간 정보

2. fact_query: 사용자 개인 정보에 대한 질문
   - "내 이름은 뭐야?", "내 직업이 뭐지?" 등
   - 사용자 프로필, 선호도, 개인사에 대한 질문

3. general_chat: 일반적인 대화, 인사, 감정 표현 등
   - "안녕", "고마워", "좋은 하루 보내" 등
   - 추상적 질문이나 철학적 질문

JSON 형식으로 응답하세요:
{{
    "intent": "search_needed|fact_query|general_chat",
    "confidence": 0.0-1.0,
    "fact_type": "user_name|job|hobby|mbti|goal|none" (fact_query인 경우만),
    "reasoning": "분류 근거를 간단히 설명"
}}
"""

        try:
            provider = self.llm_service.get_provider()
            response_content, _ = await provider.invoke(
                model="gpt-4o-mini",
                system_prompt="You are an expert at intent classification. Always respond with valid JSON.",
                user_prompt=prompt,
                request_id=f"intent_classification_{generate_id()}",
                response_format="json"
            )
            
            result = json.loads(response_content)
            
            intent_type = IntentType(result.get("intent", "unknown"))
            confidence = float(result.get("confidence", 0.0))
            reasoning = result.get("reasoning", "")
            
            fact_type = None
            if intent_type == IntentType.FACT_QUERY:
                fact_type_str = result.get("fact_type", "none")
                fact_type = FactQueryType(fact_type_str)
            
            return IntentClassificationResult(intent_type, confidence, fact_type, reasoning)
            
        except Exception as e:
            logger.error(f"LLM intent classification failed: {e}")
            raise

    def _classify_with_keywords(self, user_message: str) -> IntentClassificationResult:
        """키워드 기반 의도 분류 (fallback)"""
        message_lower = user_message.lower()
        
        # 사실 질문 감지
        for fact_type, keywords in self.fact_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                return IntentClassificationResult(
                    IntentType.FACT_QUERY, 
                    0.8, 
                    fact_type, 
                    f"Keyword match: {keywords}"
                )
        
        # 검색 필요성 감지
        if any(keyword in message_lower for keyword in self.search_keywords):
            return IntentClassificationResult(
                IntentType.SEARCH_NEEDED, 
                0.7, 
                None, 
                f"Search keyword detected"
            )
        
        # 질문어 감지
        question_words = ["언제", "어디", "누구", "무엇", "어떻게", "왜", "몇", "어느"]
        if any(word in user_message for word in question_words):
            return IntentClassificationResult(
                IntentType.SEARCH_NEEDED, 
                0.6, 
                None, 
                f"Question word detected"
            )
        
        return IntentClassificationResult(
            IntentType.GENERAL_CHAT, 
            0.5, 
            None, 
            "Default classification"
        )

    async def is_search_needed(self, user_message: str) -> bool:
        """검색이 필요한지 판단"""
        result = await self.classify_intent(user_message)
        return result.intent_type == IntentType.SEARCH_NEEDED

    async def get_fact_query_type(self, user_message: str) -> Optional[FactQueryType]:
        """사실 질문 유형 반환"""
        result = await self.classify_intent(user_message)
        if result.intent_type == IntentType.FACT_QUERY:
            return result.fact_type
        return None
