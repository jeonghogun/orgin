"""
LLM Service - Unified interface for all LLM providers with improved error handling.
Now includes both async and sync methods for use in API and Celery contexts.
"""
import asyncio
import json
import logging
import os
import re
import time
from typing import Dict, Any, Tuple, List, Optional
from abc import ABC, abstractmethod

# Import both async and sync clients
import openai

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:  # pragma: no cover - legacy OpenAI library compatibility
    OpenAI = None
    AsyncOpenAI = None
import google.generativeai as genai
import anthropic
from anthropic import Anthropic, AsyncAnthropic
try:  # pragma: no cover - optional typing helpers for newer openai SDKs
    from openai.types.chat import ChatCompletionMessageParam
except (ImportError, AttributeError):
    ChatCompletionMessageParam = Dict[str, Any]  # type: ignore[assignment]

try:  # pragma: no cover - optional typing helpers for newer openai SDKs
    from openai.types.chat.completion_create_params import ResponseFormat
except (ImportError, AttributeError):
    ResponseFormat = Dict[str, Any]  # type: ignore[assignment]

from app.config.settings import settings
from app.core.secrets import SecretProvider
from app.core.errors import LLMError, LLMErrorCode
from app.services.provider_errors import map_openai_error, map_anthropic_error, map_gemini_error
from app.services.retry_policy import retry_manager

logger = logging.getLogger(__name__)


from typing import AsyncGenerator

class LLMProvider(ABC):
    @abstractmethod
    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        pass

    @abstractmethod
    def invoke_sync(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        pass

    @abstractmethod
    async def stream_invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str) -> AsyncGenerator[str, None]:
        yield


class OpenAIProvider(LLMProvider):
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        api_key = secret_provider.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found in secret provider.")

        self.legacy_mode = False
        self.async_client: Optional[AsyncOpenAI] = None
        self.sync_client: Optional[OpenAI] = None
        self._openai_module = openai

        if AsyncOpenAI is not None and OpenAI is not None:
            try:
                self.async_client = AsyncOpenAI(api_key=api_key)
                self.sync_client = OpenAI(api_key=api_key)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning(
                    "Falling back to legacy OpenAI client due to init failure: %s", exc
                )
                self.legacy_mode = True
        else:
            self.legacy_mode = True

        if self.legacy_mode:
            logger.info("Using legacy OpenAI client compatibility mode.")
            self._openai_module.api_key = api_key

    async def _invoke_modern(
        self,
        model: str,
        messages: List[ChatCompletionMessageParam],
        response_format: str,
        request_id: str,
        start_time: float,
    ) -> Tuple[str, Dict[str, Any]]:
        response_format_config: ResponseFormat = (
            {"type": "json_object"} if response_format == "json" else {"type": "text"}
        )
        try:
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                response_format=response_format_config,
                temperature=0.7,
                max_tokens=4000,
            )
        except TypeError as type_error:
            if "response_format" in str(type_error):
                response = await self.async_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4000,
                )
            else:
                raise

        usage_data = response.usage
        content = response.choices[0].message.content or ""
        metrics = {
            "prompt_tokens": usage_data.prompt_tokens if usage_data else 0,
            "completion_tokens": usage_data.completion_tokens if usage_data else 0,
            "total_tokens": usage_data.total_tokens if usage_data else 0,
        }
        latency_ms = (time.time() - start_time) * 1000
        logger.info(
            "OpenAI API call successful",
            extra={
                "req_id": request_id,
                "provider": "openai",
                "model": model,
                "latency_ms": latency_ms,
                "tokens_used": metrics["total_tokens"],
            },
        )
        return content, metrics

    async def _invoke_legacy(
        self,
        model: str,
        messages: List[Dict[str, str]],
        response_format: str,
        request_id: str,
        start_time: float,
    ) -> Tuple[str, Dict[str, Any]]:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000,
        }
        if response_format == "json":
            # Legacy APIs do not support response_format, rely on prompt instructions.
            kwargs.setdefault("temperature", 0.0)

        chat_completion = self._openai_module.ChatCompletion
        if hasattr(chat_completion, "acreate"):
            response = await chat_completion.acreate(**kwargs)
        else:  # pragma: no cover - very old SDK fallback
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: chat_completion.create(**kwargs)
            )

        usage_data = response.get("usage", {})
        choice = response["choices"][0]
        message_content = choice.get("message", {}).get("content", "")
        metrics = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }
        latency_ms = (time.time() - start_time) * 1000
        logger.info(
            "OpenAI API call successful (legacy)",
            extra={
                "req_id": request_id,
                "provider": "openai",
                "model": model,
                "latency_ms": latency_ms,
                "tokens_used": metrics["total_tokens"],
            },
        )
        return message_content, metrics

    async def invoke(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
        response_format: str = "text",
    ) -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            if self.legacy_mode:
                return await self._invoke_legacy(
                    model, messages, response_format, request_id, start_time
                )
            return await self._invoke_modern(
                model, messages, response_format, request_id, start_time
            )
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                "OpenAI API call failed",
                extra={
                    "req_id": request_id,
                    "provider": "openai",
                    "model": model,
                    "error_code": llm_error.error_code.value,
                    "error_message": llm_error.error_message,
                    "latency_ms": latency_ms,
                    "retryable": llm_error.retryable,
                    **llm_error.to_dict(),
                },
            )
            raise llm_error

    def invoke_sync(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
        response_format: str = "text",
    ) -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            if self.legacy_mode:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 4000,
                }
                if response_format == "json":
                    kwargs.setdefault("temperature", 0.0)
                response = self._openai_module.ChatCompletion.create(**kwargs)
                usage_data = response.get("usage", {})
                content = response["choices"][0]["message"].get("content", "")
            else:
                response_format_config: ResponseFormat = (
                    {"type": "json_object"} if response_format == "json" else {"type": "text"}
                )
                try:
                    response = self.sync_client.chat.completions.create(
                        model=model,
                        messages=messages,
                        response_format=response_format_config,
                        temperature=0.7,
                        max_tokens=4000,
                    )
                except TypeError as type_error:
                    if "response_format" in str(type_error):
                        response = self.sync_client.chat.completions.create(
                            model=model,
                            messages=messages,
                            temperature=0.7,
                            max_tokens=4000,
                        )
                    else:
                        raise
                usage_data = response.usage
                content = response.choices[0].message.content or ""

            metrics = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0)
                if isinstance(usage_data, dict)
                else getattr(usage_data, "prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0)
                if isinstance(usage_data, dict)
                else getattr(usage_data, "completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0)
                if isinstance(usage_data, dict)
                else getattr(usage_data, "total_tokens", 0),
            }
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "OpenAI API call successful (sync)",
                extra={
                    "req_id": request_id,
                    "provider": "openai",
                    "model": model,
                    "latency_ms": latency_ms,
                    "tokens_used": metrics["total_tokens"],
                },
            )
            return content, metrics
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                "OpenAI API call failed (sync)",
                extra={
                    "req_id": request_id,
                    "provider": "openai",
                    "model": model,
                    "error_code": llm_error.error_code.value,
                    "error_message": llm_error.error_message,
                    "latency_ms": latency_ms,
                    "retryable": llm_error.retryable,
                    **llm_error.to_dict(),
                },
            )
            raise llm_error

    async def stream_invoke(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
    ) -> AsyncGenerator[str, None]:
        start_time = time.time()
        try:
            messages: List[ChatCompletionMessageParam] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            if self.legacy_mode:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 4000,
                    "stream": True,
                }
                stream = await self._openai_module.ChatCompletion.acreate(**kwargs)
                async for chunk in stream:
                    delta = chunk["choices"][0]["delta"].get("content") or ""
                    yield delta
            else:
                stream = await self.async_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4000,
                    stream=True,
                )
                async for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    yield content
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "OpenAI API stream completed successfully",
                extra={
                    "req_id": request_id,
                    "provider": "openai",
                    "model": model,
                    "latency_ms": latency_ms,
                },
            )
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                "OpenAI API stream failed",
                extra={
                    "req_id": request_id,
                    "provider": "openai",
                    "model": model,
                    "error_code": llm_error.error_code.value,
                    "error_message": llm_error.error_message,
                    "latency_ms": latency_ms,
                    "retryable": llm_error.retryable,
                    **llm_error.to_dict(),
                },
            )
            raise llm_error

    async def create_embedding_async(self, text: str):
        if self.legacy_mode:
            if hasattr(self._openai_module.Embedding, "acreate"):
                return await self._openai_module.Embedding.acreate(
                    model="text-embedding-ada-002", input=text
                )
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._openai_module.Embedding.create(
                    model="text-embedding-ada-002", input=text
                ),
            )
        return await self.async_client.embeddings.create(
            model="text-embedding-3-small", input=text
        )

    def create_embedding_sync(self, text: str):
        if self.legacy_mode:
            return self._openai_module.Embedding.create(
                model="text-embedding-ada-002", input=text
            )
        return self.sync_client.embeddings.create(
            model="text-embedding-3-small", input=text
        )


class MockLLMProvider(LLMProvider):
    """Fallback provider that returns deterministic responses for tests."""

    def __init__(self) -> None:
        super().__init__()

    async def invoke(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
        response_format: str = "text",
    ) -> Tuple[str, Dict[str, Any]]:
        return self._build_response(system_prompt, user_prompt, response_format)

    def invoke_sync(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
        response_format: str = "text",
    ) -> Tuple[str, Dict[str, Any]]:
        return self._build_response(system_prompt, user_prompt, response_format)

    async def stream_invoke(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        request_id: str,
    ) -> AsyncGenerator[str, None]:
        content, _ = self._build_response(system_prompt, user_prompt, "text")
        yield content

    async def create_embedding_async(self, text: str):
        return self._build_embedding_response(text)

    def create_embedding_sync(self, text: str):
        return self._build_embedding_response(text)

    def _build_embedding_response(self, text: str) -> Dict[str, Any]:
        vector = self._embedding_vector(text)
        usage = {
            "prompt_tokens": max(1, len(text.split())),
            "completion_tokens": 0,
            "total_tokens": max(1, len(text.split())),
        }
        return {"data": [{"embedding": vector}], "usage": usage}

    def _embedding_vector(self, text: str) -> List[float]:
        if not text:
            return [0.0] * 8
        seed = abs(hash(text)) % 997
        return [((seed + i) % 17) / 16.0 for i in range(8)]

    def _build_response(
        self, system_prompt: str, user_prompt: str, response_format: str
    ) -> Tuple[str, Dict[str, Any]]:
        if response_format == "json":
            payload = self._build_json_payload(user_prompt)
            content = json.dumps(payload, ensure_ascii=False)
        else:
            content = self._build_text_payload(system_prompt, user_prompt)

        metrics = self._build_metrics(user_prompt, content)
        return content, metrics

    def _build_metrics(self, user_prompt: str, content: str) -> Dict[str, int]:
        prompt_tokens = max(1, len(user_prompt.split()) or 1)
        completion_tokens = max(1, len(content.split()) or 1)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _build_text_payload(self, system_prompt: str, user_prompt: str) -> str:
        extracted = self._extract_message(user_prompt) or user_prompt.strip()
        if not extracted:
            extracted = "a follow-up"
        lowered = extracted.lower()
        if "capital of france" in lowered:
            return "The capital of France is Paris."
        if "weather" in lowered or "날씨" in lowered:
            return "It looks clear with mild temperatures in the requested location."
        if "token" in lowered and "budget" in lowered:
            return "The current usage is within the configured budget."
        summary = extracted[:200].strip()
        return f"[mock-response] {summary}" if summary else "[mock-response]"

    def _build_json_payload(self, user_prompt: str) -> Dict[str, Any]:
        lower_prompt = user_prompt.lower()
        message = self._extract_message(user_prompt)
        if "executive_summary" in lower_prompt and "strongest_consensus" in lower_prompt:
            topic_hint = self._extract_between(user_prompt, '"topic": "', '"') or self._extract_between(user_prompt, "Topic:", "\n") or "Test Topic"
            return {
                "topic": topic_hint.strip(),
                "executive_summary": "This is the executive summary.",
                "strongest_consensus": [
                    "Alternative 1 should move forward with careful monitoring.",
                    "All panelists agree to stage the rollout to manage risk.",
                ],
                "remaining_disagreements": [
                    "Budget ownership still needs to be clarified."
                ],
                "recommendations": [
                    "Alternative 1",
                    "Launch a pilot within 30 days with adoption milestones.",
                ],
                "alternatives": ["Alternative 1"],
                "recommendation": "adopt",
            }
        if "\"facts\"" in lower_prompt:
            facts = []
            if message:
                name = self._extract_name(message)
                if name:
                    facts.append({"type": "user_name", "value": name, "confidence": 0.9})
            return {"facts": facts}
        if "\"question\"" in lower_prompt:
            topic = self._extract_between(user_prompt, "topic is", "\"") or message or "이 주제"
            return {"question": f"{topic.strip()}에 대해 좀 더 자세히 알려주실 수 있을까요?"}
        if "intent" in lower_prompt and "search_needed" in lower_prompt:
            return self._simulate_classifier_intent(message)
        if "intent" in lower_prompt:
            return self._simulate_user_intent(message)
        if "final alignment round" in lower_prompt or "resolution_context" in lower_prompt:
            return {
                "round": 4,
                "no_new_arguments": False,
                "final_position": "모든 패널이 합의한 실행안을 채택합니다.",
                "consensus_highlights": [
                    "위험 관리와 성장 전략을 균형 있게 추진하기로 합의했습니다.",
                    "후속 검증 지표를 명확히 정의했습니다.",
                ],
                "open_questions": ["장기 예산 배분 계획을 어떻게 조정할지"],
                "next_steps": [
                    "30일 내 시범 프로젝트를 시작하고 결과를 공유합니다.",
                    "리스크 대응 태스크포스를 구성합니다.",
                ],
            }
        if "synthesis round" in lower_prompt or "synthesis_context" in lower_prompt:
            return {
                "round": 3,
                "no_new_arguments": False,
                "executive_summary": "핵심 성과와 리스크를 균형 있게 고려한 최종 제안을 정리했습니다.",
                "conclusion": "조직 역량을 확장하면서도 통제 가능한 범위 내에서 파일럿을 진행해야 합니다.",
                "recommendations": [
                    "파일럿 단계에서 명확한 성공 지표를 정의합니다.",
                    "리스크 완화를 위한 감시 체계를 구축합니다.",
                ],
            }
        if "rebuttal round" in lower_prompt or "rebuttal_context" in lower_prompt:
            return {
                "round": 2,
                "no_new_arguments": False,
                "agreements": ["사용자 가치 검증이 최우선이라는 점에 동의합니다."],
                "disagreements": [
                    {
                        "point": "초기 투자 규모는 다소 과도합니다.",
                        "reasoning": "현금 흐름 변동성이 커질 수 있으므로 단계적 확대가 필요합니다.",
                    }
                ],
                "additions": [
                    {
                        "point": "실행 책임자 지정과 위험 관리 플랜이 필요합니다.",
                        "reasoning": "명확한 책임 구조가 있어야 실행력이 확보됩니다.",
                    }
                ],
            }
        if "initial analysis" in lower_prompt or "initial_analysis" in lower_prompt:
            topic = self._extract_between(user_prompt, "Topic:", "\n") or "주제"
            return {
                "round": 1,
                "key_takeaway": f"{topic.strip()}에 대한 초기 분석을 완료했습니다.",
                "arguments": [
                    "시장 성장 가능성이 높으며 빠른 학습이 중요합니다.",
                    "팀 역량 강화를 위한 명확한 교육 계획이 필요합니다.",
                ],
                "risks": [
                    "과도한 확장으로 자원이 분산될 수 있습니다.",
                    "보안 및 규제 리스크를 선제적으로 점검해야 합니다.",
                ],
                "opportunities": [
                    "선제적 실행으로 브랜드 리더십을 확보할 수 있습니다.",
                    "외부 파트너십 확장을 통해 시너지를 얻을 수 있습니다.",
                ],
            }
        return {"result": "ok"}

    def _extract_message(self, prompt: str) -> str:
        patterns = [
            r"메시지:\s*\"(.+?)\"",
            r"message:\s*\"(.+?)\"",
            r"user message:\s*\"(.+?)\"",
        ]
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_between(self, text: str, start: str, end: str) -> Optional[str]:
        pattern = re.escape(start) + r"\s*(.+?)" + re.escape(end)
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _extract_name(self, message: str) -> Optional[str]:
        pattern = re.compile(r"(?:내|제|저의)\s*이름(?:은|은요|은지)?\s*([\w가-힣]+)")
        match = pattern.search(message)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r"[\s,.;!?]+$", "", candidate)
            if candidate and len(candidate) <= 10 and not any(ch.isdigit() for ch in candidate):
                return candidate
        return None

    def _simulate_user_intent(self, message: str) -> Dict[str, Any]:
        lower = message.lower()
        entities: Dict[str, Any] = {}
        if any(keyword in lower for keyword in ["시간", "몇 시", "몇시", "time"]):
            return {"intent": "time", "entities": entities, "confidence": 0.9}
        if any(keyword in lower for keyword in ["날씨", "weather", "기온", "비와", "비 와"]):
            if "서울" in message:
                entities["location"] = "서울"
            elif "busan" in lower or "부산" in message:
                entities["location"] = "부산"
            return {"intent": "weather", "entities": entities, "confidence": 0.9}
        name = self._extract_name(message)
        if name:
            return {"intent": "name_set", "entities": {"name": name}, "confidence": 0.95}
        if any(keyword in lower for keyword in ["내 이름", "name", "누구야"]):
            return {"intent": "name_get", "entities": entities, "confidence": 0.9}
        if any(keyword in lower for keyword in ["검토", "review", "토론"]):
            return {"intent": "review", "entities": entities, "confidence": 0.8}
        return {"intent": "general", "entities": entities, "confidence": 0.5}

    def _simulate_classifier_intent(self, message: str) -> Dict[str, Any]:
        lower = message.lower()
        reasoning = "Keyword analysis"
        if any(keyword in lower for keyword in ["검색", "찾아", "알려줘", "news", "latest"]):
            return {
                "intent": "search_needed",
                "confidence": 0.85,
                "fact_type": "none",
                "reasoning": reasoning,
            }
        for fact_type, keywords in {
            "user_name": ["내 이름", "제 이름", "이름이 뭐"],
            "job": ["직업"],
            "hobby": ["취미"],
            "mbti": ["mbti"],
            "goal": ["목표"],
        }.items():
            if any(keyword in message for keyword in keywords):
                return {
                    "intent": "fact_query",
                    "confidence": 0.8,
                    "fact_type": fact_type,
                    "reasoning": reasoning,
                }
        return {
            "intent": "general_chat",
            "confidence": 0.6,
            "fact_type": "none",
            "reasoning": "Default classification",
        }


class GeminiProvider(LLMProvider):
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        api_key = secret_provider.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found.")
        genai.configure(api_key=api_key)
        self._default_model_name = "gemini-pro"
        self._model_cache: Dict[str, Any] = {}

    def _get_model(self, model_name: Optional[str]) -> Any:
        target_name = model_name or self._default_model_name
        cached = self._model_cache.get(target_name)
        if cached is not None:
            return cached
        gemini_model = genai.GenerativeModel(target_name)
        self._model_cache[target_name] = gemini_model
        return gemini_model

    async def stream_invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str) -> AsyncGenerator[str, None]:
        # Placeholder implementation
        logger.warning("Streaming not implemented for Gemini, falling back to non-streaming.")
        content, _ = await self.invoke(model, system_prompt, user_prompt, request_id)
        yield content

    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        model_name = model or self._default_model_name
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            gemini_model = self._get_model(model_name)
            response = await gemini_model.generate_content_async(full_prompt)
            content = response.text
            metrics = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "Gemini API call successful",
                extra={"req_id": request_id, "provider": "gemini", "model": model_name, "latency_ms": latency_ms},
            )
            return content, metrics
        except Exception as e:
            llm_error = map_gemini_error(e, "gemini")
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                "Gemini API call failed",
                extra={
                    "req_id": request_id,
                    "provider": "gemini",
                    "model": model_name,
                    "error_code": llm_error.error_code.value,
                    "error_message": llm_error.error_message,
                    "latency_ms": latency_ms,
                    "retryable": llm_error.retryable,
                    **llm_error.to_dict(),
                },
            )
            raise llm_error

    def invoke_sync(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        model_name = model or self._default_model_name
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            gemini_model = self._get_model(model_name)
            response = gemini_model.generate_content(full_prompt)
            content = response.text
            metrics = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "Gemini API call successful (sync)",
                extra={"req_id": request_id, "provider": "gemini", "model": model_name, "latency_ms": latency_ms},
            )
            return content, metrics
        except Exception as e:
            llm_error = map_gemini_error(e, "gemini")
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                "Gemini API call failed (sync)",
                extra={
                    "req_id": request_id,
                    "provider": "gemini",
                    "model": model_name,
                    "error_code": llm_error.error_code.value,
                    "error_message": llm_error.error_message,
                    "latency_ms": latency_ms,
                    "retryable": llm_error.retryable,
                    **llm_error.to_dict(),
                },
            )
            raise llm_error


class ClaudeProvider(LLMProvider):
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        api_key = secret_provider.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key not found.")
        self.async_client = AsyncAnthropic(api_key=api_key)
        self.sync_client = Anthropic(api_key=api_key)

    async def stream_invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str) -> AsyncGenerator[str, None]:
        # Placeholder implementation
        logger.warning("Streaming not implemented for Claude, falling back to non-streaming.")
        content, _ = await self.invoke(model, system_prompt, user_prompt, request_id)
        yield content

    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            response = await self.async_client.messages.create(model=model, system=system_prompt, messages=[{"role": "user", "content": user_prompt}], max_tokens=4000)
            content = response.content[0].text
            metrics = {"prompt_tokens": response.usage.input_tokens, "completion_tokens": response.usage.output_tokens, "total_tokens": response.usage.input_tokens + response.usage.output_tokens}
            latency_ms = (time.time() - start_time) * 1000
            logger.info("Anthropic API call successful", extra={"req_id": request_id, "provider": "claude", "model": model, "latency_ms": latency_ms, "tokens_used": metrics["total_tokens"]})
            return content, metrics
        except Exception as e:
            llm_error = map_anthropic_error(e, "claude")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("Anthropic API call failed", extra={"req_id": request_id, "provider": "claude", "model": model, "error_code": llm_error.error_code.value, "error_message": llm_error.error_message, "latency_ms": latency_ms, "retryable": llm_error.retryable, **llm_error.to_dict()})
            raise llm_error

    def invoke_sync(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            response = self.sync_client.messages.create(model=model, system=system_prompt, messages=[{"role": "user", "content": user_prompt}], max_tokens=4000)
            content = response.content[0].text
            metrics = {"prompt_tokens": response.usage.input_tokens, "completion_tokens": response.usage.output_tokens, "total_tokens": response.usage.input_tokens + response.usage.output_tokens}
            latency_ms = (time.time() - start_time) * 1000
            logger.info("Anthropic API call successful (sync)", extra={"req_id": request_id, "provider": "claude", "model": model, "latency_ms": latency_ms, "tokens_used": metrics["total_tokens"]})
            return content, metrics
        except Exception as e:
            llm_error = map_anthropic_error(e, "claude")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("Anthropic API call failed (sync)", extra={"req_id": request_id, "provider": "claude", "model": model, "error_code": llm_error.error_code.value, "error_message": llm_error.error_message, "latency_ms": latency_ms, "retryable": llm_error.retryable, **llm_error.to_dict()})
            raise llm_error


class LLMService:
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        self.secret_provider = secret_provider
        self.providers: Dict[str, LLMProvider] = {}
        self._initialized = False
        self._mock_provider: Optional[MockLLMProvider] = None
        self._initialization_errors: Dict[str, str] = {}

    def _initialize_providers(self):
        if self._initialized:
            return

        if settings.MOCK_LLM:
            logger.info("MOCK_LLM flag enabled; using deterministic mock provider.")
            self.providers = {"mock": self._ensure_mock_provider()}
            self._initialized = True
            return

        self.providers = {}
        self._initialization_errors = {}

        openai_key = self.secret_provider.get("OPENAI_API_KEY")
        if openai_key:
            try:
                self.providers["openai"] = OpenAIProvider(self.secret_provider)
                logger.info("OpenAI provider initialized.")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Failed to initialize OpenAI provider: %s", exc, exc_info=True)
                self._initialization_errors["openai"] = str(exc)
        else:
            self._initialization_errors["openai"] = "OPENAI_API_KEY is not configured."

        gemini_key = self.secret_provider.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                self.providers["gemini"] = GeminiProvider(self.secret_provider)
                logger.info("Gemini provider initialized.")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Failed to initialize Gemini provider: %s", exc, exc_info=True)
                self._initialization_errors["gemini"] = str(exc)
        else:
            self._initialization_errors["gemini"] = "GEMINI_API_KEY is not configured."

        anthropic_key = self.secret_provider.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                self.providers["claude"] = ClaudeProvider(self.secret_provider)
                logger.info("Claude provider initialized.")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Failed to initialize Claude provider: %s", exc, exc_info=True)
                self._initialization_errors["claude"] = str(exc)
        else:
            self._initialization_errors["claude"] = "ANTHROPIC_API_KEY is not configured."

        if not self.providers:
            if self._allow_mock_provider():
                logger.info(
                    "No external LLM providers available; using deterministic mock provider for this run."
                )
                self.providers["mock"] = self._ensure_mock_provider()
                self._initialized = True
                return

            issues = "; ".join(
                f"{name}: {reason}" for name, reason in sorted(self._initialization_errors.items())
            ) or "No provider configuration detected."
            error_message = (
                "No LLM providers could be initialized. "
                f"{issues} Configure a provider API key or set MOCK_LLM=1 for local development."
            )
            raise LLMError(
                error_code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                provider=settings.LLM_PROVIDER,
                error_message=error_message,
                retryable=False,
            )

        self._initialized = True
        logger.info("LLM service initialized with providers: %s", list(self.providers.keys()))

    def _allow_mock_provider(self) -> bool:
        if settings.MOCK_LLM:
            return True
        if settings.TESTING:
            return True
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True
        env_name = settings.ENVIRONMENT.lower()
        return env_name in {"test", "testing"}

    def get_provider(self, provider_name: str = "openai") -> LLMProvider:
        try:
            self._initialize_providers()
        except LLMError:
            raise

        if provider_name not in self.providers:
            if settings.FORCE_DEFAULT_PROVIDER:
                default_provider = settings.LLM_PROVIDER
                if default_provider in self.providers:
                    logger.warning(
                        "Provider '%s' unavailable; forcing default provider '%s'.",
                        provider_name,
                        default_provider,
                    )
                    return self.providers[default_provider]

            available = ", ".join(sorted(self.providers.keys())) or "none"
            raise LLMError(
                error_code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                provider=provider_name,
                retryable=False,
                error_message=(
                    f"Provider '{provider_name}' is not configured. "
                    f"Available providers: {available}. "
                    "Set MOCK_LLM=1 to enable the deterministic mock provider in local development."
                ),
            )

        return self.providers[provider_name]

    def _ensure_mock_provider(self) -> MockLLMProvider:
        if self._mock_provider is None:
            self._mock_provider = MockLLMProvider()
            self.providers.setdefault("mock", self._mock_provider)
        return self._mock_provider

    def get_or_create_provider(self, provider_name: str = "openai") -> LLMProvider:
        """Return a provider, falling back to the deterministic mock when unavailable."""
        try:
            return self.get_provider(provider_name)
        except LLMError as exc:
            if exc.error_code == LLMErrorCode.PROVIDER_UNAVAILABLE and self._allow_mock_provider():
                logger.info(
                    "Provider '%s' unavailable; using mock provider for this request.",
                    provider_name,
                )
                return self._ensure_mock_provider()
            raise

    def get_available_providers(self) -> List[str]:
        """Return a list of provider identifiers that are ready to serve requests."""
        self._initialize_providers()
        return list(self.providers.keys())

    # --- ASYNC METHODS for FastAPI ---
    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text", provider_name: str = "openai") -> Tuple[str, Dict[str, Any]]:
        return await self.invoke_with_retry(provider_name, model, system_prompt, user_prompt, request_id, response_format)

    async def invoke_with_retry(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        async def _invoke():
            provider = self.get_or_create_provider(provider_name)
            return await provider.invoke(model, system_prompt, user_prompt, request_id, response_format)
        return await retry_manager.execute_with_retry(_invoke, provider_name)

    async def stream_invoke(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str) -> AsyncGenerator[str, None]:
        provider = self.get_or_create_provider(provider_name)
        # Note: Retry logic is not applied to streaming calls by default, as it's more complex.
        # A robust implementation might buffer the stream and retry on specific errors.
        async for chunk in provider.stream_invoke(model, system_prompt, user_prompt, request_id):
            yield chunk

    async def generate_embedding(self, text: str) -> Tuple[List[float], Dict[str, Any]]:
        provider = self.get_or_create_provider("openai")
        if not isinstance(provider, (OpenAIProvider, MockLLMProvider)):
            raise TypeError("Embedding generation is only supported for OpenAI provider.")
        try:
            response = await provider.create_embedding_async(text)
            data = response.data[0] if hasattr(response, "data") else response["data"][0]
            if isinstance(data, dict):
                embedding = data.get("embedding")
            else:
                embedding = getattr(data, "embedding", None)
            if embedding is None:
                raise ValueError("Embedding data missing from OpenAI response")
            usage_data = getattr(response, "usage", None)
            if isinstance(response, dict):
                usage_data = response.get("usage")
            metrics = {
                "prompt_tokens": getattr(usage_data, "prompt_tokens", 0)
                if usage_data
                else (usage_data.get("prompt_tokens", 0) if isinstance(usage_data, dict) else 0),
                "completion_tokens": 0,
                "total_tokens": getattr(usage_data, "prompt_tokens", 0)
                if usage_data
                else (usage_data.get("prompt_tokens", 0) if isinstance(usage_data, dict) else 0),
            }
            return embedding, metrics
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            logger.error(
                f"OpenAI embedding generation failed: {llm_error.error_message}"
            )
            raise llm_error

    # --- SYNC METHODS for Celery ---
    def invoke_sync(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        return self.invoke_with_retry_sync(provider_name, model, system_prompt, user_prompt, request_id, response_format)

    def invoke_with_retry_sync(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        def _invoke_sync():
            provider = self.get_or_create_provider(provider_name)
            return provider.invoke_sync(model, system_prompt, user_prompt, request_id, response_format)
        return retry_manager.execute_with_retry_sync(_invoke_sync, provider_name)

    def generate_embedding_sync(self, text: str) -> Tuple[List[float], Dict[str, Any]]:
        provider = self.get_or_create_provider("openai")
        if not isinstance(provider, (OpenAIProvider, MockLLMProvider)):
            raise TypeError("Embedding generation is only supported for OpenAI provider.")
        try:
            response = provider.create_embedding_sync(text)
            data = response.data[0] if hasattr(response, "data") else response["data"][0]
            if isinstance(data, dict):
                embedding = data.get("embedding")
            else:
                embedding = getattr(data, "embedding", None)
            if embedding is None:
                raise ValueError("Embedding data missing from OpenAI response")
            usage_data = getattr(response, "usage", None)
            if isinstance(response, dict):
                usage_data = response.get("usage")
            metrics = {
                "prompt_tokens": getattr(usage_data, "prompt_tokens", 0)
                if usage_data
                else (usage_data.get("prompt_tokens", 0) if isinstance(usage_data, dict) else 0),
                "completion_tokens": 0,
                "total_tokens": getattr(usage_data, "prompt_tokens", 0)
                if usage_data
                else (usage_data.get("prompt_tokens", 0) if isinstance(usage_data, dict) else 0),
            }
            return embedding, metrics
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            logger.error(
                f"OpenAI embedding generation failed (sync): {llm_error.error_message}"
            )
            raise llm_error

    # --- Common Methods ---
    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        return retry_manager.get_provider_status()


# Global service instance
llm_service: "LLMService" = None

def get_llm_service() -> "LLMService":
    global llm_service
    if llm_service is None:
        from app.core.secrets import env_secrets_provider
        llm_service = LLMService(secret_provider=env_secrets_provider)
    return llm_service
