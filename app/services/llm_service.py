"""
LLM Service - Unified interface for all LLM providers
"""

import json
import logging
from typing import Dict, Any
from abc import ABC, abstractmethod

import openai
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
    ) -> Dict[str, Any]:
        """Invoke LLM with prompts"""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation"""

    def __init__(self):
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
    ) -> Dict[str, Any]:
        """Invoke OpenAI API"""
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response_format_config = (
                {"type": "json_object"} if response_format == "json" else None
            )

            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format=response_format_config,
                temperature=0.7,
                max_tokens=4000,
            )

            usage_data = response.usage
            return {
                "content": response.choices[0].message.content,
                "model": model,
                "provider": "openai",
                "request_id": request_id,
                "metrics": {
                    "prompt_tokens": usage_data.prompt_tokens,
                    "completion_tokens": usage_data.completion_tokens,
                    "total_tokens": usage_data.total_tokens,
                }
            }

        except Exception as e:
            logger.error(f"OpenAI API error: {e}", extra={"req_id": request_id})
            raise


class LLMService:
    """Main LLM service orchestrator"""

    def __init__(self):
        self.providers = {}
        self._initialized = False

    def _initialize_providers(self):
        """Lazy initialization of providers"""
        if self._initialized:
            return

        try:
            if not settings.OPENAI_API_KEY:
                logger.warning("OpenAI API key is not configured. LLM service will be disabled.")
                self.providers = {}
                self._initialized = True
                return

            self.providers = {"openai": OpenAIProvider()}
            self._initialized = True
            logger.info("LLM providers initialized successfully")
        except Exception as e:
            logger.warning(f"LLM provider initialization failed: {e}")
            self.providers = {}

    def get_provider(self, provider_name: str = "openai") -> LLMProvider:
        """Get LLM provider instance"""
        self._initialize_providers()
        if provider_name not in self.providers:
            raise ValueError(f"Unsupported provider: {provider_name}")
        return self.providers[provider_name]

    async def generate_panel_analysis(
        self, topic: str, persona: str, instruction: str, request_id: str
    ) -> Dict[str, Any]:
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

        response = await provider.invoke(
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=request_id,
            response_format="json",
        )

        return response

    async def generate_consolidated_report(
        self,
        topic: str,
        round_number: int,
        mode: str,
        panel_reports: list,
        request_id: str,
    ) -> Dict[str, Any]:
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

        response = await provider.invoke(
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=request_id,
            response_format="json",
        )

        return response


    async def summarize_for_debate(self, panelist_output: str, request_id: str) -> str:
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

        response = await provider.invoke(
            model=settings.LLM_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_id=request_id,
            response_format="text",
        )

        return response.get("content", "")


# Global LLM service instance
llm_service = LLMService()
