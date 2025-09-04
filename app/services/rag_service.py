"""
RAG (Retrieval-Augmented Generation) Service
"""
import logging
import json
import asyncio
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass, field

from app.services.external_api_service import ExternalSearchService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.storage_service import StorageService
from app.models.schemas import Message
from app.models.memory_schemas import ConversationContext, UserProfile, ContextUpdate
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

@dataclass
class RAGContext:
    user_query: str
    intent: str
    entities: Dict[str, str]
    user_profile: Optional[UserProfile]
    conversation_context: Optional[ConversationContext]
    search_results: List[Dict[str, str]] = field(default_factory=list)
    wiki_summary: Optional[str] = None
    relevant_memories: List[Message] = field(default_factory=list)
    user_facts: List[Dict[str, Any]] = field(default_factory=list)

class RAGService:
    def __init__(self, search_service: ExternalSearchService, llm_service: LLMService, memory_service: MemoryService, storage_service: StorageService):
        self.search_service = search_service
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.storage_service = storage_service

    async def generate_rag_response(self, room_id: str, user_id: str, user_message: str, intent: str, entities: Dict[str, str], request_id: str) -> str:
        try:
            rag_context = await self._collect_context(room_id, user_id, user_message, intent, entities)
            await self._enhance_with_external_data(rag_context)
            rag_prompt = self._build_rag_prompt(rag_context)
            response = await self._generate_llm_response(rag_prompt, request_id)
            await self._update_context_after_rag_response(room_id, user_id, user_message, response, rag_context)
            return response
        except Exception as e:
            logger.error(f"Failed to generate RAG response: {e}", exc_info=True)
            return "죄송합니다. RAG 기반 응답을 생성할 수 없습니다."

    async def stream_rag_response(self, room_id: str, user_id: str, user_message: str) -> AsyncGenerator[str, None]:
        request_id = generate_id() # Generate a unique ID for this request
        try:
            # For streaming, we'll use a simplified intent/entity process
            intent = "general"
            entities = {}

            rag_context = await self._collect_context(room_id, user_id, user_message, intent, entities)
            await self._enhance_with_external_data(rag_context)
            rag_prompt = self._build_rag_prompt(rag_context)

            # Use the new streaming method from LLMService
            provider_name = "openai" # or determine dynamically
            model = "gpt-3.5-turbo"

            full_response = ""
            async for chunk in self.llm_service.stream_invoke(provider_name, model, "You are a helpful AI assistant.", rag_prompt, request_id):
                full_response += chunk
                yield chunk

            # After the stream is complete, update the context
            await self._update_context_after_rag_response(room_id, user_id, user_message, full_response, rag_context)

        except Exception as e:
            logger.error(f"Failed to generate streaming RAG response: {e}", exc_info=True)
            yield "죄송합니다. 스트리밍 응답을 생성하는 중 오류가 발생했습니다."

    async def _collect_context(self, room_id: str, user_id: str, user_message: str, intent: str, entities: Dict[str, str]) -> RAGContext:
        current_room = self.storage_service.get_room(room_id)
        if not current_room:
            raise ValueError(f"Room with id {room_id} not found.")

        user_profile_task = self.memory_service.get_user_profile(user_id)

        room_ids_to_search = [room_id]
        if current_room.type == "sub" and current_room.parent_id:
            room_ids_to_search.append(current_room.parent_id)

        relevant_memories_task = self.memory_service.get_relevant_memories_hybrid(query=user_message, room_ids=room_ids_to_search, user_id=user_id)
        conversation_context_task = self.memory_service.get_context(room_id, user_id)
        user_facts_task = self.memory_service.get_user_facts(user_id)

        user_profile, relevant_memories, conversation_context, user_facts = await asyncio.gather(
            user_profile_task, relevant_memories_task, conversation_context_task, user_facts_task
        )

        if current_room.type == "sub" and current_room.parent_id:
            parent_context = await self.memory_service.get_context(current_room.parent_id, user_id)
            if parent_context and parent_context.summary:
                if conversation_context and conversation_context.summary:
                    conversation_context.summary = f"Parent Room Context: {parent_context.summary}\n\nCurrent Room Context: {conversation_context.summary}"
                elif conversation_context:
                    conversation_context.summary = f"Parent Room Context: {parent_context.summary}"

        return RAGContext(
            user_profile=user_profile, conversation_context=conversation_context,
            relevant_memories=relevant_memories, user_facts=user_facts,
            user_query=user_message, intent=intent, entities=entities
        )

    def _build_rag_prompt(self, rag_context: RAGContext) -> str:
        prompt_parts = ["You are an AI assistant. Use the following context to provide a helpful and accurate response."]
        if rag_context.user_profile:
            profile_info = []
            if rag_context.user_profile.name: profile_info.append(f"User's name: {rag_context.user_profile.name}")
            if rag_context.user_profile.interests: profile_info.append(f"Interests: {', '.join(rag_context.user_profile.interests)}")
            if profile_info: prompt_parts.append("--- User Profile ---\n" + "\n".join(profile_info))
        if rag_context.user_facts:
            facts_str = "\n".join([f"- {fact['key']}: {fact['value_json']}" for fact in rag_context.user_facts])
            prompt_parts.append("--- Known Facts ---\n" + facts_str)
        if rag_context.conversation_context and rag_context.conversation_context.summary:
            prompt_parts.append(f"--- Conversation Summary ---\n{rag_context.conversation_context.summary}")
        if rag_context.relevant_memories:
            memories_str = "\n".join([f"- {mem.content}" for mem in rag_context.relevant_memories])
            prompt_parts.append("--- Relevant Past Conversations ---\n" + memories_str)
        if rag_context.search_results:
            search_str = "\n".join([f"- {res['title']}: {res['snippet']}" for res in rag_context.search_results])
            prompt_parts.append("--- Web Search Results ---\n" + search_str)
        prompt_parts.append(f"\n--- User's Question ---\n{rag_context.user_query}")
        prompt_parts.append("\nResponse:")
        return "\n\n".join(prompt_parts)

    async def _generate_llm_response(self, rag_prompt: str, request_id: str) -> str:
        provider = self.llm_service.get_provider()
        content, _ = await provider.invoke(model="gpt-3.5-turbo", system_prompt="You are a helpful AI assistant.", user_prompt=rag_prompt, request_id=request_id, response_format="text")
        return content

    async def _update_context_after_rag_response(self, room_id: str, user_id: str, user_message: str, ai_response: str, rag_context: RAGContext):
        # This is a simplified context update. A real implementation would be more sophisticated.
        existing_summary = rag_context.conversation_context.summary if rag_context.conversation_context else ""
        new_summary = f"{existing_summary}\nUser: {user_message}\nAI: {ai_response}".strip()

        # In a real app, we'd use an LLM to summarize and extract topics/sentiment
        context_update = ContextUpdate(
            room_id=room_id, user_id=user_id, summary=new_summary[-2000:], # Keep it from growing too large
            key_topics=[], sentiment="neutral"
        )
        await self.memory_service.update_context(context_update)

    async def _enhance_with_external_data(self, rag_context: RAGContext):
        # Placeholder for brevity
        pass

    async def generate_observer_qa_response(self, question: str, report_content: Dict[str, Any]) -> str:
        """
        Answers a user's question based on the content of a final review report.
        """
        try:
            # Flatten the report content into a string for the prompt
            report_str = json.dumps(report_content, ensure_ascii=False, indent=2)

            prompt = f"""
            당신은 AI 토론의 최종 보고서를 분석하고 설명하는 '관측자' AI입니다.
            주어진 최종 보고서 내용을 바탕으로 사용자의 질문에 답변하세요.
            보고서에 없는 내용은 답변하지 마세요.

            --- 최종 보고서 ---
            {report_str}
            ---

            사용자 질문: "{question}"

            답변:
            """

            provider = self.llm_service.get_provider()
            content, _ = await provider.invoke(
                model="gpt-4-turbo", # Use a powerful model for accurate QA
                system_prompt="You are an AI observer, answering questions about a provided report.",
                user_prompt=prompt,
                request_id="observer_qa",
                response_format="text"
            )
            return content
        except Exception as e:
            logger.error(f"Failed to generate Observer QA response: {e}", exc_info=True)
            return "죄송합니다. 보고서에 대한 답변을 생성하는 중 오류가 발생했습니다."
