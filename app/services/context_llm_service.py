"""
Context-Aware LLM Service
"""

import logging
from typing import List, Optional
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.models.memory_schemas import (
    ConversationContext,
    UserProfile,
    ContextUpdate,
    MemoryEntry,
)

logger = logging.getLogger(__name__)


class ContextLLMService:
    """맥락을 고려한 LLM 서비스"""

    def __init__(self, llm_service: LLMService, memory_service: MemoryService):
        super().__init__()
        self.llm_service = llm_service
        self.memory_service = memory_service

    async def generate_contextual_response(
        self, room_id: str, user_id: str, user_message: str, request_id: str
    ) -> str:
        """맥락을 고려한 응답 생성"""
        try:
            # 1. 사용자 프로필 조회
            user_profile = await self.memory_service.get_user_profile(user_id)

            # 2. 대화 맥락 조회
            context = await self.memory_service.get_context(room_id, user_id)

            # 3. 관련 메모리 조회
            relevant_memories = await self.memory_service.get_relevant_memories(
                room_id, user_id, user_message, limit=3
            )

            # 4. 맥락 기반 프롬프트 구성
            context_prompt = self._build_context_prompt(
                user_profile, context, relevant_memories, user_message
            )

            # 5. LLM 응답 생성
            provider = self.llm_service.get_provider()
            response_text, _ = await provider.invoke(
                model="gpt-3.5-turbo",
                system_prompt="당신은 맥락을 이해하고 기억하는 친근한 AI 어시스턴트입니다.",
                user_prompt=context_prompt,
                request_id=request_id,
                response_format="text",
            )

            # 6. 맥락 업데이트
            await self._update_context_after_response(
                room_id, user_id, user_message, response_text
            )

            return response_text

        except Exception as e:
            logger.error(f"Failed to generate contextual response: {e}")
            return "죄송합니다. 맥락을 고려한 응답을 생성할 수 없습니다."

    def _build_context_prompt(
        self,
        user_profile: Optional[UserProfile],
        context: Optional[ConversationContext],
        memories: List[MemoryEntry],
        user_message: str,
    ) -> str:
        """맥락 기반 프롬프트 구성"""

        prompt_parts: List[str] = []

        # 시스템 역할 설정
        prompt_parts.append(
            "당신은 맥락을 이해하고 기억하는 친근한 AI 어시스턴트입니다."
        )

        # 사용자 프로필 정보
        if user_profile:
            profile_info: List[str] = []
            if user_profile.name:
                profile_info.append(f"사용자 이름: {user_profile.name}")
            if user_profile.interests:
                profile_info.append(f"관심사: {', '.join(user_profile.interests)}")
            if user_profile.conversation_style:
                profile_info.append(f"대화 스타일: {user_profile.conversation_style}")

            if profile_info:
                prompt_parts.append("사용자 정보:\n" + "\n".join(profile_info))

        # 대화 맥락 정보
        if context and context.summary:
            prompt_parts.append(f"이전 대화 요약: {context.summary}")

        if context and context.key_topics:
            prompt_parts.append(f"주요 주제: {', '.join(context.key_topics)}")

        # 관련 메모리 정보
        if memories:
            memory_info: List[str] = []
            for memory in memories:
                memory_info.append(f"- {memory.key}: {memory.value}")

            if memory_info:
                prompt_parts.append("관련 기억:\n" + "\n".join(memory_info))

        # 현재 사용자 메시지
        prompt_parts.append(f"\n사용자: {user_message}")
        prompt_parts.append("AI: ")

        return "\n\n".join(prompt_parts)

    async def _update_context_after_response(
        self, room_id: str, user_id: str, user_message: str, ai_response: str
    ) -> None:
        """응답 후 맥락 업데이트"""
        try:
            # 간단한 맥락 요약 생성 (실제로는 LLM을 사용하여 더 정교하게 처리 가능)
            context_summary = (
                f"사용자가 '{user_message}'라고 말했고, AI가 응답했습니다."
            )

            # 주요 주제 추출 (간단한 키워드 기반)
            key_topics = self._extract_key_topics(user_message + " " + ai_response)

            # 감정 분석 (간단한 키워드 기반)
            sentiment = self._analyze_sentiment(user_message + " " + ai_response)

            # 맥락 업데이트
            context_update = ContextUpdate(
                room_id=room_id,
                user_id=user_id,
                summary=context_summary,
                key_topics=key_topics,
                sentiment=sentiment,
            )

            await self.memory_service.update_context(context_update)

        except Exception as e:
            logger.error(f"Failed to update context after response: {e}")

    def _extract_key_topics(self, text: str) -> List[str]:
        """주요 주제 추출 (간단한 키워드 기반)"""
        # 간단한 키워드 매칭 (실제로는 더 정교한 NLP 사용 가능)
        keywords = [
            "시간",
            "날씨",
            "검색",
            "위키",
            "이름",
            "프로젝트",
            "일정",
            "음식",
            "영화",
            "음악",
            "운동",
            "건강",
            "여행",
            "취미",
            "일",
            "학습",
            "기술",
            "AI",
            "인공지능",
            "프로그래밍",
        ]

        found_topics: List[str] = []
        for keyword in keywords:
            if keyword in text:
                found_topics.append(keyword)

        return found_topics[:5]  # 최대 5개 주제

    def _analyze_sentiment(self, text: str) -> str:
        """감정 분석 (간단한 키워드 기반)"""
        positive_words = ["좋아", "감사", "행복", "즐거", "재미", "훌륭", "완벽"]
        negative_words = ["싫어", "화나", "슬프", "짜증", "불만", "실망", "어려워"]

        text_lower = text.lower()

        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"

    async def update_user_profile_from_message(
        self, user_id: str, message: str
    ) -> None:
        """메시지에서 사용자 프로필 정보 추출 및 업데이트"""
        try:
            # 기존 프로필 조회
            profile = await self.memory_service.get_user_profile(user_id)
            if not profile:
                profile = UserProfile(user_id=user_id, created_at=0, updated_at=0)

            # 이름 추출 (간단한 패턴 매칭)
            if "내 이름은" in message or "저는" in message:
                # 간단한 이름 추출 로직
                words = message.split()
                for i, word in enumerate(words):
                    if word in ["이름은", "저는"] and i + 1 < len(words):
                        name = (
                            words[i + 1]
                            .replace("입니다", "")
                            .replace("이야", "")
                            .replace("야", "")
                        )
                        if len(name) > 1:  # 의미있는 이름인지 확인
                            profile.name = name
                            break

            # 관심사 추출
            interest_keywords = ["좋아하는", "관심", "취미", "즐겨", "재미있어"]

            for keyword in interest_keywords:
                if keyword in message:
                    # 간단한 관심사 추출
                    words = message.split()
                    for i, word in enumerate(words):
                        if keyword in word and i + 1 < len(words):
                            interest = words[i + 1]
                            if profile.interests and interest not in profile.interests:
                                profile.interests.append(interest)
                            elif not profile.interests:
                                profile.interests = [interest]
                            break

            # 프로필 업데이트
            await self.memory_service.update_user_profile(profile)

        except Exception as e:
            logger.error(f"Failed to update user profile from message: {e}")
