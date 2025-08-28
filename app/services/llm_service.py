"""
LLM Service - Unified interface for all LLM providers
"""

import json
import logging
from typing import Dict, Any, Tuple, List
from abc import ABC, abstractmethod

import openai
import google.generativeai as genai
import anthropic
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from app.config.settings import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    async def invoke(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
        response_format: str = "text",
    ) -> Tuple[str, Dict[str, Any]]:
        """Invoke LLM with prompts"""
        pass


from typing import Dict, Any, Tuple, List, Optional

class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation"""

    def __init__(self, client: Optional[openai.AsyncOpenAI] = None):
        super().__init__()
        if client:
            self.client = client
        else:
            if not settings.OPENAI_API_KEY:
                raise ValueError(
                    "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable."
                )
            self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def invoke(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
        response_format: str = "text",
    ) -> Tuple[str, Dict[str, Any]]:
        """Invoke OpenAI API"""
        try:
            messages: List[ChatCompletionMessageParam] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response_format_config: ResponseFormat = (
                {"type": "json_object"} if response_format == "json" else {"type": "text"}
            )

            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format=response_format_config,
                temperature=0.7,
                max_tokens=4000,
            )

            usage_data = response.usage
            content = response.choices[0].message.content or ""
            metrics = {
                "prompt_tokens": usage_data.prompt_tokens if usage_data else 0,
                "completion_tokens": usage_data.completion_tokens if usage_data else 0,
                "total_tokens": usage_data.total_tokens if usage_data else 0,
            }
            return content, metrics

        except Exception as e:
            logger.error(f"OpenAI API error: {e}", extra={"req_id": request_id})
            raise


class GeminiProvider(LLMProvider):
    """LLM provider for Google Gemini models"""

    def __init__(self):
        super().__init__()
        if not settings.GEMINI_API_KEY:
            raise ValueError("Gemini API key is not configured.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')

    async def invoke(
        self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text"
    ) -> Tuple[str, Dict[str, Any]]:
        # Gemini API has a different way of handling system prompts. We combine them.
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        try:
            response = await self.model.generate_content_async(full_prompt)
            content = response.text
            # Gemini API (v1) does not provide token usage metrics in the response
            metrics = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            return content, metrics
        except Exception as e:
            logger.error(f"Gemini API error: {e}", extra={"req_id": request_id})
            raise

class ClaudeProvider(LLMProvider):
    """LLM provider for Anthropic Claude models"""

    def __init__(self):
        super().__init__()
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("Anthropic API key is not configured.")
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def invoke(
        self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text"
    ) -> Tuple[str, Dict[str, Any]]:
        try:
            response = await self.client.messages.create(
                model=model, # e.g., "claude-3-opus-20240229"
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=4000,
            )
            content = response.content[0].text
            metrics = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
            return content, metrics
        except Exception as e:
            logger.error(f"Anthropic API error: {e}", extra={"req_id": request_id})
            raise


class LLMService:
    """Main LLM service orchestrator"""

    def __init__(self):
        super().__init__()
        self.providers = {}
        self._initialized = False

    def _initialize_providers(self):
        """Lazy initialization of providers"""
        if self._initialized:
            return

        self.providers = {}

        # Initialize OpenAI
        if settings.OPENAI_API_KEY:
            try:
                self.providers["openai"] = OpenAIProvider()
                logger.info("OpenAI provider initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI provider: {e}")

        # Initialize Gemini
        if settings.GEMINI_API_KEY:
            try:
                self.providers["gemini"] = GeminiProvider()
                logger.info("Gemini provider initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini provider: {e}")

        # Initialize Claude
        if settings.ANTHROPIC_API_KEY:
            try:
                self.providers["claude"] = ClaudeProvider()
                logger.info("Claude provider initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude provider: {e}")

        self._initialized = True
        logger.info(f"LLM service initialized with providers: {list(self.providers.keys())}")

    def get_provider(self, provider_name: str = "openai") -> LLMProvider:
        """Get LLM provider instance"""
        self._initialize_providers()
        if provider_name not in self.providers:
            raise ValueError(f"Unsupported provider: {provider_name}")
        return self.providers[provider_name]

    async def generate_panel_analysis(
        self, topic: str, persona: str, instruction: str, request_id: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate panel analysis using LLM"""
        provider = self.get_provider()

        system_prompt = f"""당신은 {persona} 역할을 맡은 전문가입니다.
주어진 주제에 대해 전문적이고 객관적인 분석을 제공하세요.
일반인이 이해할 수 있도록 쉬운 용어를 사용하고, 전문 용어는 괄호로 설명을 추가하세요."""

        user_prompt = f"""주제: {topic}
지시사항: {instruction}

다음 JSON 형식으로 분석 결과를 제공하세요:
{{
    "summary": "전체 분석 요약 (3-4줄)",
    "key_points": ["주요 포인트 1", "주요 포인트 2", "주요 포인트 3"],
    "concerns": ["우려사항 1", "우려사항 2"],
    "recommendations": ["권고사항 1", "권고사항 2"]
}}"""

        content, metrics = await provider.invoke(
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=request_id,
            response_format="json",
        )

        return content, metrics

    async def generate_embedding(self, text: str) -> Tuple[List[float], Dict[str, Any]]:
        """Generate embedding for a given text."""
        provider = self.get_provider()
        # Assuming the provider has an embedding method.
        # For OpenAI, it's a separate client endpoint.
        try:
            response = await self.providers["openai"].client.embeddings.create(
                input=[text],
                model="text-embedding-3-small" # Or another model
            )
            embedding = response.data[0].embedding
            usage = response.usage
            metrics = {
                "prompt_tokens": usage.prompt_tokens,
                "total_tokens": usage.total_tokens,
            }
            return embedding, metrics
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise

    async def generate_consolidated_report(
        self,
        topic: str,
        round_number: int,
        mode: str,
        panel_reports: List[Any],
        request_id: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate consolidated report from panel reports"""
        provider = self.get_provider()

        system_prompt = """당신은 여러 전문가 분석을 종합하여 의사결정자를 위한 최종 실행 가능한 보고서를 작성하는 마스터 전략가입니다.
패널 의견들 간의 관계와 충돌을 분석하여 새로운 통찰을 도출하세요. 단순히 요약하지 마세요."""

        user_prompt = f"""주제: {topic}
라운드: {round_number}
모드: {mode}

패널 분석 결과:
{json.dumps(panel_reports, indent=2, ensure_ascii=False)}

다음 JSON 형식으로 종합 보고서를 작성하세요:
{{
    "topic": "{topic}",
    "executive_summary": "전체 논의에 대한 3줄 요약",
    "perspective_summary": {{
        "persona_1": {{"positive": "주요 긍정적 관점", "negative": "주요 부정적 관점"}},
        "persona_2": {{"positive": "주요 긍정적 관점", "negative": "주요 부정적 관점"}}
    }},
    "alternatives": ["분석을 바탕으로 원래 아이디어에 대한 1-2개의 구체적인 대안 제시"],
    "recommendation": "adopt",
    "round_summary": "이번 라운드의 핵심 논의 사항과 주요 결론 (3줄 요약)",
    "evidence_sources": ["주요 근거와 출처들 (링크나 참고자료 포함)"]
}}"""

        content, metrics = await provider.invoke(
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=request_id,
            response_format="json",
        )

        return content, metrics


    async def summarize_for_debate(
        self, panelist_output: str, request_id: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Summarizes a panelist's output for use in the next debate turn for other panelists.
        """
        provider = self.get_provider()

        system_prompt = """You are a summarization AI for a multi-agent debate system. Your task is to create a concise summary of a panelist's argument for the other panelists to read. Follow these rules strictly:
1.  Extract only the most essential elements: the main claim, key evidence/reasoning, and the overall tone (e.g., agree, oppose, propose an alternative).
2.  Keep the summary very short, ideally 1-3 sentences and under 200 tokens.
3.  **Crucially, you must preserve critical details exactly as they appear.** This includes:
    - Code snippets (e.g., `function(arg)`)
    - Dates and numbers (e.g., `2025-10-26`, `3.14159`)
    - Specific names, JIRA tickets, or other identifiers.
4.  Remove all filler, greetings, meta-comments, and conversational fluff.
5.  If there are multiple points, focus on the 1-2 most important ones that are most relevant to the debate.
"""

        user_prompt = f"""Please summarize the following panelist's output:

--- PANEL OUTPUT ---
{panelist_output}
--- END PANEL OUTPUT ---

Concise summary for other panelists:"""

        content, metrics = await provider.invoke(
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=request_id,
            response_format="text",
        )

        return content, metrics


