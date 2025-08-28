"""
RAG (Retrieval-Augmented Generation) Service
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from app.services.external_api_service import ExternalSearchService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.storage_service import StorageService
from app.models.memory_schemas import ConversationContext, UserProfile, MemoryEntry

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """RAG 컨텍스트 정보"""

    user_profile: Optional[UserProfile]
    conversation_context: Optional[ConversationContext]
    search_results: List[Dict[str, str]]
    wiki_summary: Optional[str]
    relevant_memories: List[MemoryEntry]
    user_query: str
    intent: str
    entities: Dict[str, str]


class RAGService:
    """RAG (Retrieval-Augmented Generation) 서비스"""

    def __init__(
        self,
        search_service: ExternalSearchService,
        llm_service: LLMService,
        memory_service: MemoryService,
        storage_service: StorageService,
    ):
        super().__init__()
        self.search_service = search_service
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.storage_service = storage_service

    async def generate_rag_response(
        self,
        room_id: str,
        user_id: str,
        user_message: str,
        intent: str,
        entities: Dict[str, str],
        request_id: str,
    ) -> str:
        """RAG 기반 응답 생성"""
        try:
            # 1. 컨텍스트 수집 (메모리 상속 로직 추가)
            rag_context = await self._collect_context(
                room_id, user_id, user_message, intent, entities
            )

            # 2. 외부 정보 검색 (필요시)
            await self._enhance_with_external_data(rag_context)

            # 3. RAG 프롬프트 구성
            rag_prompt = self._build_rag_prompt(rag_context)

            # 4. LLM 응답 생성
            response = await self._generate_llm_response(rag_prompt, request_id)

            # 5. 컨텍스트 업데이트
            await self._update_context_after_rag_response(
                room_id, user_id, user_message, response, rag_context
            )

            return response

        except Exception as e:
            logger.error(f"Failed to generate RAG response: {e}")
            return "죄송합니다. RAG 기반 응답을 생성할 수 없습니다."

    async def _collect_context(
        self,
        room_id: str,
        user_id: str,
        user_message: str,
        intent: str,
        entities: Dict[str, str],
    ) -> RAGContext:
        """컨텍스트 정보 수집 (메모리 상속 로직 포함)"""
        # Get current room to check its type and parent
        current_room = await self.storage_service.get_room(room_id)
        if not current_room:
            # This should ideally not happen if called from a valid context
            raise ValueError(f"Room with id {room_id} not found.")

        # Always fetch the user's general profile
        user_profile = await self.memory_service.get_user_profile(user_id)

        # --- Memory Inheritance and Retrieval Logic ---
        room_ids_to_search = [room_id]
        if current_room.type == "sub" and current_room.parent_id:
            logger.info(f"Sub room {room_id} inheriting memory from main room {current_room.parent_id}")
            room_ids_to_search.append(current_room.parent_id)

        # Fetch relevant memories from all specified rooms in a single query
        relevant_memories = await self.memory_service.get_relevant_memories(
            room_ids=room_ids_to_search,
            user_id=user_id,
            query_text=user_message,
            limit=5,  # Fetch a slightly larger pool of memories
        )

        # Fetch conversation context (summary) for the current room
        conversation_context = await self.memory_service.get_context(room_id, user_id)

        # If it's a sub-room, fetch and prepend the parent's context summary
        if current_room.type == "sub" and current_room.parent_id:
            parent_context = await self.memory_service.get_context(current_room.parent_id, user_id)
            if parent_context and parent_context.summary:
                if conversation_context and conversation_context.summary:
                    conversation_context.summary = (
                        f"Parent Room Context: {parent_context.summary}\n\n"
                        f"Current Room Context: {conversation_context.summary}"
                    )
                elif conversation_context:
                    conversation_context.summary = f"Parent Room Context: {parent_context.summary}"

        return RAGContext(
            user_profile=user_profile,
            conversation_context=conversation_context,
            search_results=[],
            wiki_summary=None,
            relevant_memories=relevant_memories,
            user_query=user_message,
            intent=intent,
            entities=entities,
        )

    async def _enhance_with_external_data(self, rag_context: RAGContext) -> None:
        """외부 데이터로 컨텍스트 강화"""
        try:
            # 검색 결과 추가 (일반적인 질문이나 최신 정보가 필요한 경우)
            if self._needs_search(rag_context):
                query = self._extract_search_query(rag_context)
                if query:
                    # 더 많은 검색 결과를 가져와서 필터링
                    raw_results = await self.search_service.web_search(query, 10)
                    filtered_results = self._filter_and_rank_search_results(
                        raw_results, query
                    )
                    rag_context.search_results = filtered_results[:3]  # 최종 3개만 사용

            # 위키 정보 추가 (특정 주제에 대한 상세 정보가 필요한 경우)
            if self._needs_wiki(rag_context):
                topic = self._extract_wiki_topic(rag_context)
                if topic:
                    wiki_summary = await self.search_service.wiki_summary(topic)
                    if wiki_summary:
                        rag_context.wiki_summary = self._validate_wiki_content(
                            wiki_summary
                        )

        except Exception as e:
            logger.error(f"Failed to enhance with external data: {e}")

    def _needs_search(self, rag_context: RAGContext) -> bool:
        """검색이 필요한지 판단"""
        # 일반적인 질문이나 최신 정보가 필요한 경우
        search_keywords = [
            "최신",
            "최근",
            "현재",
            "어떻게",
            "무엇",
            "어디",
            "언제",
            "왜",
            "방법",
            "기법",
            "트렌드",
            "동향",
            "뉴스",
            "정보",
        ]

        query_lower = rag_context.user_query.lower()
        return any(keyword in query_lower for keyword in search_keywords)

    def _needs_wiki(self, rag_context: RAGContext) -> bool:
        """위키 정보가 필요한지 판단"""
        # 특정 주제나 개념에 대한 상세 정보가 필요한 경우
        wiki_keywords = [
            "무엇",
            "정의",
            "개념",
            "역사",
            "발전",
            "원리",
            "구조",
            "특징",
            "장점",
            "단점",
            "비교",
            "분류",
        ]

        query_lower = rag_context.user_query.lower()
        return any(keyword in query_lower for keyword in wiki_keywords)

    def _extract_search_query(self, rag_context: RAGContext) -> Optional[str]:
        """맥락을 고려한 검색 쿼리 추출"""
        # 기본 사용자 쿼리
        base_query = rag_context.user_query.strip()

        # 맥락 정보 수집
        context_parts: List[str] = []

        # 이전 대화 요약이 있으면 추가
        if (
            rag_context.conversation_context
            and rag_context.conversation_context.summary
        ):
            context_parts.append(rag_context.conversation_context.summary)

        # 주요 주제가 있으면 추가
        if (
            rag_context.conversation_context
            and rag_context.conversation_context.key_topics
        ):
            context_parts.extend(rag_context.conversation_context.key_topics)

        # 관련 메모리가 있으면 추가
        if rag_context.relevant_memories:
            for memory in rag_context.relevant_memories:
                context_parts.append(f"{memory.key}: {memory.value}")

        # 맥락을 포함한 검색 쿼리 구성
        if context_parts:
            context_str = " ".join(context_parts)
            # 맥락 + 현재 질문으로 검색 쿼리 구성
            enhanced_query = f"{context_str} {base_query}"
        else:
            enhanced_query = base_query

        # 불필요한 단어 제거
        stop_words = [
            "이",
            "가",
            "을",
            "를",
            "의",
            "에",
            "로",
            "으로",
            "와",
            "과",
            "도",
            "만",
            "은",
            "는",
        ]
        for word in stop_words:
            enhanced_query = enhanced_query.replace(word, " ")

        # 쿼리 길이 제한 (너무 길면 잘라내기)
        enhanced_query = enhanced_query.strip()
        if len(enhanced_query) > 200:
            # 현재 질문을 우선하고, 맥락은 앞부분만 사용
            words = enhanced_query.split()
            if len(words) > 30:
                enhanced_query = " ".join(words[:30])

        return enhanced_query if len(enhanced_query) > 2 else None

    def _extract_wiki_topic(self, rag_context: RAGContext) -> Optional[str]:
        """위키 주제 추출"""
        # 사용자 메시지에서 위키 검색할 주제 추출
        query = rag_context.user_query.strip()

        # 명사나 주제어 추출 (간단한 방식)
        # 실제로는 더 정교한 NLP 사용 가능
        words = query.split()
        if len(words) >= 2:
            return words[0] + " " + words[1]  # 첫 두 단어 조합
        elif len(words) == 1:
            return words[0]

        return None

    def _build_rag_prompt(self, rag_context: RAGContext) -> str:
        """RAG 프롬프트 구성"""
        prompt_parts: List[str] = []

        # 시스템 역할 설정
        prompt_parts.append(
            (
                "당신은 외부 정보를 활용하여 정확하고 유용한 답변을 제공하는 AI 어시스턴트입니다. "
                "제공된 정보를 바탕으로 사용자의 질문에 답변하되, 다음 사항을 반드시 지켜주세요:\n"
                "1. 검색 결과나 위키 정보가 있으면 그것을 우선적으로 참조하세요\n"
                "2. 정보를 간결하고 명확하게 요약하여 제공하세요\n"
                "3. 최신 정보임을 강조하고, 출처는 1-2개만 명시하세요\n"
                "4. 이전 대화 맥락을 고려하여 연속성 있는 답변을 제공하세요\n"
                "5. 사용자의 이름을 사용하여 친근하게 답변하세요\n"
                "6. 검색 결과를 그대로 나열하지 말고, 핵심 내용만 요약하여 자연스럽게 답변하세요"
            )
        )

        # 사용자 프로필 정보
        if rag_context.user_profile:
            profile_info: List[str] = []
            if rag_context.user_profile.name:
                profile_info.append(f"사용자 이름: {rag_context.user_profile.name}")
            if rag_context.user_profile.interests:
                profile_info.append(
                    f"관심사: {', '.join(rag_context.user_profile.interests)}"
                )

            if profile_info:
                prompt_parts.append("사용자 정보:\n" + "\n".join(profile_info))

        # 대화 맥락 정보
        if (
            rag_context.conversation_context
            and rag_context.conversation_context.summary
        ):
            prompt_parts.append(
                f"이전 대화 맥락: {rag_context.conversation_context.summary}"
            )

        # 관련 메모리 정보
        if rag_context.relevant_memories:
            memory_info: List[str] = []
            for memory in rag_context.relevant_memories:
                memory_info.append(f"- {memory.key}: {memory.value}")

            if memory_info:
                prompt_parts.append("관련 기억:\n" + "\n".join(memory_info))

        # 검색 결과 정보 (요약된 형태로 제공)
        if rag_context.search_results:
            # 검색 결과를 요약하여 제공
            summarized_results = self._summarize_search_results(
                rag_context.search_results
            )
            prompt_parts.append(f"🔍 검색 결과 요약:\n{summarized_results}")
        else:
            prompt_parts.append(
                "⚠️ 검색 결과가 없습니다. 일반적인 지식으로 답변하겠습니다."
            )

        # 위키 정보
        if rag_context.wiki_summary:
            prompt_parts.append(f"위키백과 정보:\n{rag_context.wiki_summary}")

        # 사용자 질문
        prompt_parts.append(f"\n사용자 질문: {rag_context.user_query}")
        prompt_parts.append(
            "\n위의 정보를 바탕으로 친근하고 정확한 답변을 제공해주세요:"
        )

        return "\n\n".join(prompt_parts)

    async def _generate_llm_response(self, rag_prompt: str, request_id: str) -> str:
        """LLM 응답 생성"""
        try:
            provider = self.llm_service.get_provider()
            content, _ = await provider.invoke(
                model="gpt-3.5-turbo",
                system_prompt="당신은 외부 정보를 활용하여 정확하고 유용한 답변을 제공하는 AI 어시스턴트입니다.",
                user_prompt=rag_prompt,
                request_id=request_id,
                response_format="text",
            )
            return content
        except Exception as e:
            logger.error(f"Failed to generate LLM response: {e}")
            return "죄송합니다. 응답을 생성할 수 없습니다."

    async def _update_context_after_rag_response(
        self,
        room_id: str,
        user_id: str,
        user_message: str,
        ai_response: str,
        rag_context: RAGContext,
    ) -> None:
        """RAG 응답 후 컨텍스트 업데이트"""
        try:
            from app.models.memory_schemas import ContextUpdate

            # 기존 맥락과 새로운 정보를 결합한 요약 생성
            existing_summary = ""
            if (
                rag_context.conversation_context
                and rag_context.conversation_context.summary
            ):
                existing_summary = rag_context.conversation_context.summary + " "

            # 새로운 대화 요약 생성
            new_summary = f"{existing_summary}사용자가 '{user_message}'에 대해 질문했고, AI가 맥락을 고려하여 답변했습니다."

            # 주요 주제 추출 (기존 + 새로운 주제 결합)
            existing_topics = []
            if (
                rag_context.conversation_context
                and rag_context.conversation_context.key_topics
            ):
                existing_topics = rag_context.conversation_context.key_topics

            new_topics = self._extract_key_topics(user_message + " " + ai_response)

            # 중복 제거하고 결합
            all_topics = list(set(existing_topics + new_topics))[:5]  # 최대 5개

            # 감정 분석
            sentiment = self._analyze_sentiment(user_message + " " + ai_response)

            # 맥락 업데이트
            context_update = ContextUpdate(
                room_id=room_id,
                user_id=user_id,
                summary=new_summary,
                key_topics=all_topics,
                sentiment=sentiment,
            )

            await self.memory_service.update_context(context_update)

        except Exception as e:
            logger.error(f"Failed to update context after RAG response: {e}")

    def _extract_key_topics(self, text: str) -> List[str]:
        """주요 주제 추출"""
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
            "최신",
            "트렌드",
            "뉴스",
            "정보",
            "방법",
            "기법",
        ]

        found_topics: List[str] = []
        for keyword in keywords:
            if keyword in text:
                found_topics.append(keyword)

        return found_topics[:5]

    def _filter_and_rank_search_results(
        self, results: List[Dict[str, str]], query: str
    ) -> List[Dict[str, str]]:
        """검색 결과 필터링 및 랭킹"""
        if not results:
            return []

        scored_results: List[Tuple[int, Dict[str, str]]] = []
        query_lower = query.lower()

        for result in results:
            score = 0
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            link = result.get("link", "").lower()

            # 1. 제목 관련성 점수 (가장 중요)
            title_words = title.split()
            query_words = query_lower.split()
            title_match = sum(
                1
                for word in query_words
                if any(word in title_word for title_word in title_words)
            )
            score += title_match * 10

            # 2. 스니펫 관련성 점수
            snippet_words = snippet.split()
            snippet_match = sum(
                1
                for word in query_words
                if any(word in snippet_word for snippet_word in snippet_words)
            )
            score += snippet_match * 5

            # 3. 도메인 신뢰성 점수
            trusted_domains = [
                "wikipedia.org",
                "stackoverflow.com",
                "github.com",
                "medium.com",
                "techcrunch.com",
                "arstechnica.com",
                "ieee.org",
                "acm.org",
                "researchgate.net",
                "arxiv.org",
                "scholar.google.com",
            ]
            domain_score = sum(3 for domain in trusted_domains if domain in link)
            score += domain_score

            # 4. 최신성 점수 (URL에 연도가 포함된 경우)
            import re

            year_pattern = r"20[12]\d"  # 2010년 이후
            if re.search(year_pattern, link) or re.search(year_pattern, title):
                score += 5

            # 5. 스팸/광고 필터링
            spam_keywords = [
                "click",
                "buy",
                "discount",
                "sale",
                "advertisement",
                "sponsored",
            ]
            if any(keyword in title or keyword in snippet for keyword in spam_keywords):
                score -= 10

            # 6. 내용 길이 점수 (너무 짧거나 긴 것은 제외)
            content_length = len(title) + len(snippet)
            if 50 <= content_length <= 500:
                score += 3
            elif content_length < 20:
                score -= 5

            scored_results.append((score, result))

        # 점수순으로 정렬하고 상위 결과만 반환
        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [result for score, result in scored_results if score > 0]

    def _summarize_search_results(self, results: List[Dict[str, str]]) -> str:
        """검색 결과 요약 및 정리"""
        if not results:
            return "검색 결과가 없습니다."

        # 상위 2개 결과만 사용
        top_results = results[:2]

        summary_parts: List[str] = []

        for i, result in enumerate(top_results, 1):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            link = result.get("link", "")

            # 제목에서 핵심 키워드 추출
            title_words = title.split()
            if len(title_words) > 8:
                title = " ".join(title_words[:8]) + "..."

            # 스니펫 요약 (100자 이내)
            if len(snippet) > 100:
                snippet = snippet[:100] + "..."

            # 도메인 추출
            domain = self._extract_domain(link)

            summary_parts.append(
                f"{i}. {title}\n   {snippet}\n   출처: {domain}"
            )

        return "\n\n".join(summary_parts)

    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc
            # www 제거
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return url[:30] + "..." if len(url) > 30 else url

    def _validate_wiki_content(self, wiki_content: str) -> str:
        """위키 내용 검증 및 정리"""
        if not wiki_content:
            return ""

        # 너무 짧은 내용 필터링
        if len(wiki_content) < 50:
            return ""

        # HTML 태그 제거 (간단한 정리)
        import re

        cleaned_content = re.sub(r"<[^>]+>", "", wiki_content)

        # 중복 공백 제거
        cleaned_content = re.sub(r"\s+", " ", cleaned_content).strip()

        return cleaned_content

    def _analyze_sentiment(self, text: str) -> str:
        """감정 분석"""
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


