"""
LLM Service - Unified interface for all LLM providers with improved error handling.
Now includes both async and sync methods for use in API and Celery contexts.
"""
import json
import logging
import time
from typing import Dict, Any, Tuple, List, Optional
from abc import ABC, abstractmethod

# Import both async and sync clients
import openai
from openai import OpenAI, AsyncOpenAI
import google.generativeai as genai
import anthropic
from anthropic import Anthropic, AsyncAnthropic
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import ResponseFormat

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
        self.async_client = AsyncOpenAI(api_key=api_key)
        self.sync_client = OpenAI(api_key=api_key)

    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            messages: List[ChatCompletionMessageParam] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            response_format_config: ResponseFormat = {"type": "json_object"} if response_format == "json" else {"type": "text"}
            response = await self.async_client.chat.completions.create(model=model, messages=messages, response_format=response_format_config, temperature=0.7, max_tokens=4000)
            usage_data = response.usage
            content = response.choices[0].message.content or ""
            metrics = {"prompt_tokens": usage_data.prompt_tokens if usage_data else 0, "completion_tokens": usage_data.completion_tokens if usage_data else 0, "total_tokens": usage_data.total_tokens if usage_data else 0}
            latency_ms = (time.time() - start_time) * 1000
            logger.info("OpenAI API call successful", extra={"req_id": request_id, "provider": "openai", "model": model, "latency_ms": latency_ms, "tokens_used": metrics["total_tokens"]})
            return content, metrics
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("OpenAI API call failed", extra={"req_id": request_id, "provider": "openai", "model": model, "error_code": llm_error.error_code.value, "error_message": llm_error.error_message, "latency_ms": latency_ms, "retryable": llm_error.retryable, **llm_error.to_dict()})
            raise llm_error

    def invoke_sync(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            messages: List[ChatCompletionMessageParam] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            response_format_config: ResponseFormat = {"type": "json_object"} if response_format == "json" else {"type": "text"}
            response = self.sync_client.chat.completions.create(model=model, messages=messages, response_format=response_format_config, temperature=0.7, max_tokens=4000)
            usage_data = response.usage
            content = response.choices[0].message.content or ""
            metrics = {"prompt_tokens": usage_data.prompt_tokens if usage_data else 0, "completion_tokens": usage_data.completion_tokens if usage_data else 0, "total_tokens": usage_data.total_tokens if usage_data else 0}
            latency_ms = (time.time() - start_time) * 1000
            logger.info("OpenAI API call successful (sync)", extra={"req_id": request_id, "provider": "openai", "model": model, "latency_ms": latency_ms, "tokens_used": metrics["total_tokens"]})
            return content, metrics
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("OpenAI API call failed (sync)", extra={"req_id": request_id, "provider": "openai", "model": model, "error_code": llm_error.error_code.value, "error_message": llm_error.error_message, "latency_ms": latency_ms, "retryable": llm_error.retryable, **llm_error.to_dict()})
            raise llm_error

    async def stream_invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str) -> AsyncGenerator[str, None]:
        start_time = time.time()
        try:
            messages: List[ChatCompletionMessageParam] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            stream = await self.async_client.chat.completions.create(
                model=model, messages=messages, temperature=0.7, max_tokens=4000, stream=True
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                yield content
            latency_ms = (time.time() - start_time) * 1000
            logger.info("OpenAI API stream completed successfully", extra={"req_id": request_id, "provider": "openai", "model": model, "latency_ms": latency_ms})
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("OpenAI API stream failed", extra={"req_id": request_id, "provider": "openai", "model": model, "error_code": llm_error.error_code.value, "error_message": llm_error.error_message, "latency_ms": latency_ms, "retryable": llm_error.retryable, **llm_error.to_dict()})
            raise llm_error


class GeminiProvider(LLMProvider):
    def __init__(self, secret_provider: SecretProvider):
        super().__init__()
        api_key = secret_provider.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    async def stream_invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str) -> AsyncGenerator[str, None]:
        # Placeholder implementation
        logger.warning("Streaming not implemented for Gemini, falling back to non-streaming.")
        content, _ = await self.invoke(model, system_prompt, user_prompt, request_id)
        yield content

    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = await self.model.generate_content_async(full_prompt)
            content = response.text
            metrics = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            latency_ms = (time.time() - start_time) * 1000
            logger.info("Gemini API call successful", extra={"req_id": request_id, "provider": "gemini", "model": model, "latency_ms": latency_ms})
            return content, metrics
        except Exception as e:
            llm_error = map_gemini_error(e, "gemini")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("Gemini API call failed", extra={"req_id": request_id, "provider": "gemini", "model": model, "error_code": llm_error.error_code.value, "error_message": llm_error.error_message, "latency_ms": latency_ms, "retryable": llm_error.retryable, **llm_error.to_dict()})
            raise llm_error

    def invoke_sync(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = self.model.generate_content(full_prompt) # Sync version
            content = response.text
            metrics = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            latency_ms = (time.time() - start_time) * 1000
            logger.info("Gemini API call successful (sync)", extra={"req_id": request_id, "provider": "gemini", "model": model, "latency_ms": latency_ms})
            return content, metrics
        except Exception as e:
            llm_error = map_gemini_error(e, "gemini")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("Gemini API call failed (sync)", extra={"req_id": request_id, "provider": "gemini", "model": model, "error_code": llm_error.error_code.value, "error_message": llm_error.error_message, "latency_ms": latency_ms, "retryable": llm_error.retryable, **llm_error.to_dict()})
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
            default_provider = "openai"
            if default_provider not in self.providers:
                raise LLMError(error_code=LLMErrorCode.PROVIDER_UNAVAILABLE, provider=provider_name, retryable=False, error_message=f"No LLM providers are available. Requested: {provider_name}")
            logger.warning(f"Provider '{provider_name}' not available, falling back to '{default_provider}'.")
            return self.providers[default_provider]
        return self.providers[provider_name]

    # --- ASYNC METHODS for FastAPI ---
    async def invoke(self, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text", provider_name: str = "openai") -> Tuple[str, Dict[str, Any]]:
        return await self.invoke_with_retry(provider_name, model, system_prompt, user_prompt, request_id, response_format)

    async def invoke_with_retry(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        provider = self.get_provider(provider_name)
        async def _invoke():
            return await provider.invoke(model, system_prompt, user_prompt, request_id, response_format)
        return await retry_manager.execute_with_retry(_invoke, provider_name)

    async def stream_invoke(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str) -> AsyncGenerator[str, None]:
        provider = self.get_provider(provider_name)
        # Note: Retry logic is not applied to streaming calls by default, as it's more complex.
        # A robust implementation might buffer the stream and retry on specific errors.
        async for chunk in provider.stream_invoke(model, system_prompt, user_prompt, request_id):
            yield chunk

    async def generate_embedding(self, text: str) -> Tuple[List[float], Dict[str, Any]]:
        provider = self.get_provider("openai")
        if not isinstance(provider, OpenAIProvider):
            raise TypeError("Embedding generation is only supported for OpenAI provider.")
        try:
            response = await provider.async_client.embeddings.create(model="text-embedding-3-small", input=text)
            embedding = response.data[0].embedding
            usage_data = response.usage
            metrics = {"prompt_tokens": usage_data.prompt_tokens if usage_data else 0, "completion_tokens": 0, "total_tokens": usage_data.prompt_tokens if usage_data else 0}
            return embedding, metrics
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            logger.error(f"OpenAI embedding generation failed: {llm_error.error_message}")
            raise llm_error

    # --- SYNC METHODS for Celery ---
    def invoke_sync(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        return self.invoke_with_retry_sync(provider_name, model, system_prompt, user_prompt, request_id, response_format)

    def invoke_with_retry_sync(self, provider_name: str, model: str, system_prompt: str, user_prompt: str, request_id: str, response_format: str = "text") -> Tuple[str, Dict[str, Any]]:
        provider = self.get_provider(provider_name)
        def _invoke_sync():
            return provider.invoke_sync(model, system_prompt, user_prompt, request_id, response_format)
        return retry_manager.execute_with_retry_sync(_invoke_sync, provider_name)

    def generate_embedding_sync(self, text: str) -> Tuple[List[float], Dict[str, Any]]:
        provider = self.get_provider("openai")
        if not isinstance(provider, OpenAIProvider):
            raise TypeError("Embedding generation is only supported for OpenAI provider.")
        try:
            response = provider.sync_client.embeddings.create(model="text-embedding-3-small", input=text)
            embedding = response.data[0].embedding
            usage_data = response.usage
            metrics = {"prompt_tokens": usage_data.prompt_tokens if usage_data else 0, "completion_tokens": 0, "total_tokens": usage_data.prompt_tokens if usage_data else 0}
            return embedding, metrics
        except Exception as e:
            llm_error = map_openai_error(e, "openai")
            logger.error(f"OpenAI embedding generation failed (sync): {llm_error.error_message}")
            raise llm_error

    # --- Common Methods ---
    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        return retry_manager.get_provider_status()
