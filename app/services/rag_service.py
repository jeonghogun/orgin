"""
RAG (Retrieval-Augmented Generation) Service
"""
import logging
import json
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from app.services.external_api_service import ExternalSearchService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.storage_service import StorageService
from app.models.schemas import ConversationContext, UserProfile, Message, ContextUpdate

logger = logging.getLogger(__name__)

@dataclass
class RAGContext:
    user_profile: Optional[UserProfile]
    conversation_context: Optional[ConversationContext]
    search_results: List[Dict[str, str]] = field(default_factory=list)
    wiki_summary: Optional[str] = None
    relevant_memories: List[Message] = field(default_factory=list)
    user_facts: List[Dict[str, Any]] = field(default_factory=list)
    user_query: str
    intent: str
    entities: Dict[str, str]

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

    async def _collect_context(self, room_id: str, user_id: str, user_message: str, intent: str, entities: Dict[str, str]) -> RAGContext:
        current_room = await self.storage_service.get_room(room_id)
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
