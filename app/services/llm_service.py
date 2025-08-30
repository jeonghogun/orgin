"""
LLM Service - Unified interface for all LLM providers
"""
import json
import logging
from typing import Dict, Any, Tuple, List, Optional
from abc import ABC, abstractmethod

import openai
import google.generativeai as genai
import anthropic
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from app.config.settings import settings
from app.core.secrets import SecretProvider

logger = logging.getLogger(__name__)

class LLMProvider(ABC):
    @abstractmethod
    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        pass

class OpenAIProvider(LLMProvider):
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        api_key = secret_provider.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found in secret provider.")
        self.client = openai.AsyncOpenAI(api_key=api_key)

    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        try:
            messages: List[ChatCompletionMessageParam] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            response_format_config: ResponseFormat = {"type": "json_object"} if response_format == "json" else {"type": "text"}
            response = await self.client.chat.completions.create(model=model, messages=messages, response_format=response_format_config, temperature=0.7, max_tokens=4000)
            usage_data = response.usage
            content = response.choices[0].message.content or ""
            metrics = {"prompt_tokens": usage_data.prompt_tokens if usage_data else 0, "completion_tokens": usage_data.completion_tokens if usage_data else 0, "total_tokens": usage_data.total_tokens if usage_data else 0}
            return content, metrics
        except Exception as e:
            logger.error(f"OpenAI API error: {e}", extra={"req_id": request_id})
            raise

class GeminiProvider(LLMProvider):
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        api_key = secret_provider.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        try:
            response = await self.model.generate_content_async(full_prompt)
            content = response.text
            metrics = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            return content, metrics
        except Exception as e:
            logger.error(f"Gemini API error: {e}", extra={"req_id": request_id})
            raise

class ClaudeProvider(LLMProvider):
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        api_key = secret_provider.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key not found.")
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        try:
            response = await self.client.messages.create(model=model, system=system_prompt, messages=[{"role": "user", "content": user_prompt}], max_tokens=4000)
            content = response.content[0].text
            metrics = {"prompt_tokens": response.usage.input_tokens, "completion_tokens": response.usage.output_tokens, "total_tokens": response.usage.input_tokens + response.usage.output_tokens}
            return content, metrics
        except Exception as e:
            logger.error(f"Anthropic API error: {e}", extra={"req_id": request_id})
            raise

class LLMService:
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        self.secret_provider = secret_provider
        self.providers: Dict[str, LLMProvider] = {}
        self._initialized = False

    def _initialize_providers(self):
        if self._initialized:
            return

        if self.secret_provider.get("OPENAI_API_KEY"):
            try:
                self.providers["openai"] = OpenAIProvider(self.secret_provider)
                logger.info("OpenAI provider initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI provider: {e}")

        if self.secret_provider.get("GEMINI_API_KEY"):
            try:
                self.providers["gemini"] = GeminiProvider(self.secret_provider)
                logger.info("Gemini provider initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini provider: {e}")

        if self.secret_provider.get("ANTHROPIC_API_KEY"):
            try:
                self.providers["claude"] = ClaudeProvider(self.secret_provider)
                logger.info("Claude provider initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude provider: {e}")

        self._initialized = True
        logger.info(f"LLM service initialized with providers: {list(self.providers.keys())}")

    def get_provider(self, provider_name: str = "openai") -> LLMProvider:
        self._initialize_providers()
        if provider_name not in self.providers:
            # Fallback to default if requested provider is not available
            default_provider = "openai"
            if default_provider not in self.providers:
                raise ValueError("No LLM providers are available.")
            logger.warning(f"Provider '{provider_name}' not available, falling back to '{default_provider}'.")
            return self.providers[default_provider]
        return self.providers[provider_name]

    async def generate_embedding(self, text: str) -> Tuple[List[float], Dict[str, Any]]:
        # Embedding generation is often tied to a specific provider (e.g., OpenAI)
        provider = self.get_provider("openai") # Explicitly use openai for embeddings
        if not isinstance(provider, OpenAIProvider):
            raise TypeError("Embedding generation is only supported for OpenAI provider.")
        try:
            response = await provider.client.embeddings.create(input=[text], model="text-embedding-3-small")
            embedding = response.data[0].embedding
            usage = response.usage
            metrics = {"prompt_tokens": usage.prompt_tokens, "total_tokens": usage.total_tokens}
            return embedding, metrics
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise

    # ... other methods like generate_panel_analysis, etc. remain the same ...
    # They already use get_provider(), so they will benefit from the lazy-init and abstraction.
    async def generate_panel_analysis(self, topic: str, persona: str, instruction: str, request_id: str) -> Tuple[str, Dict[str, Any]]:
        provider = self.get_provider()
        system_prompt = f"""당신은 {persona} 역할을 맡은 전문가입니다. 주어진 주제에 대해 전문적이고 객관적인 분석을 제공하세요."""
        user_prompt = f"""주제: {topic}\n지시사항: {instruction}\n\n다음 JSON 형식으로 분석 결과를 제공하세요:\n{{\n    "summary": "...",\n    "key_points": ["..."],\n    "concerns": ["..."],\n    "recommendations": ["..."]\n}}"""
        return await provider.invoke(model=settings.LLM_MODEL, system_prompt=system_prompt, user_prompt=user_prompt, request_id=request_id, response_format="json")

    async def generate_persona_summary(self, message_history: str, request_id: str) -> Tuple[str, Dict[str, Any]]:
        provider = self.get_provider()
        system_prompt = """You are an expert user profile analyst. Your task is to analyze the provided conversation history and create a concise, structured summary of the user's persona."""
        user_prompt = f"""Based on the following conversation history, please analyze the user's persona.\n\n--- HISTORY ---\n{message_history}\n--- END HISTORY ---\n\nPlease provide the analysis in JSON format:\n{{\n    "conversation_style": "...",\n    "interests": ["..."]\n}}"""
        return await provider.invoke(model=settings.LLM_MODEL, system_prompt=system_prompt, user_prompt=user_prompt, request_id=request_id, response_format="json")

    async def generate_consolidated_report(self, topic: str, round_number: int, mode: str, panel_reports: List[Any], request_id: str) -> Tuple[str, Dict[str, Any]]:
        provider = self.get_provider()
        system_prompt = """당신은 여러 전문가 분석을 종합하여 의사결정자를 위한 최종 실행 가능한 보고서를 작성하는 마스터 전략가입니다."""
        user_prompt = f"""주제: {topic}\n라운드: {round_number}\n모드: {mode}\n\n패널 분석 결과:\n{json.dumps(panel_reports, indent=2, ensure_ascii=False)}\n\n다음 JSON 형식으로 종합 보고서를 작성하세요:\n{{\n    "topic": "{topic}",\n    "executive_summary": "...",\n    "perspective_summary": {{ ... }},\n    "alternatives": ["..."],\n    "recommendation": "...",\n    "round_summary": "...",\n    "evidence_sources": ["..."]\n}}"""
        return await provider.invoke(model=settings.LLM_MODEL, system_prompt=system_prompt, user_prompt=user_prompt, request_id=request_id, response_format="json")

    async def summarize_for_debate(self, panelist_output: str, request_id: str) -> Tuple[str, Dict[str, Any]]:
        provider = self.get_provider()
        system_prompt = """You are a summarization AI for a multi-agent debate system. Your task is to create a concise summary of a panelist's argument for the other panelists to read."""
        user_prompt = f"""Please summarize the following panelist's output:\n\n--- PANEL OUTPUT ---\n{panelist_output}\n--- END PANEL OUTPUT ---\n\nConcise summary for other panelists:"""
        return await provider.invoke(model=settings.LLM_MODEL, system_prompt=system_prompt, user_prompt=user_prompt, request_id=request_id, response_format="text")
