import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional

import openai
from anthropic import AsyncAnthropic
from google.generativeai import GenerativeModel, configure, types as genai_types
from openai.types.chat import ChatCompletionChunk

import redis
from redis.exceptions import RedisError
from app.config.settings import get_effective_redis_url, settings
from app.models.conversation_schemas import SSEEvent, SSEDelta, SSEToolCall, SSEUsage
from app.core.metrics import LLM_CALLS_TOTAL, LLM_LATENCY_SECONDS, LLM_TOKENS_TOTAL, CONVO_COST_USD_TOTAL

logger = logging.getLogger(__name__)

# Configure clients at module level with graceful fallbacks for missing secrets.
openai_client: Optional[openai.AsyncOpenAI]
anthropic_client: Optional[AsyncAnthropic]

if settings.OPENAI_API_KEY:
    try:
        # Try to create client without any additional parameters
        openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client: {e}. Using None.")
        openai_client = None
else:
    openai_client = None
    logger.warning("OPENAI_API_KEY not configured; OpenAIAdapter will return mock responses.")

if settings.ANTHROPIC_API_KEY:
    try:
        anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    except Exception as e:
        logger.warning(f"Failed to initialize Anthropic client: {e}. Using None.")
        anthropic_client = None
else:
    anthropic_client = None
    logger.info("ANTHROPIC_API_KEY not configured; AnthropicAdapter will operate in placeholder mode.")

if settings.GEMINI_API_KEY:
    configure(api_key=settings.GEMINI_API_KEY)

class BaseLLMAdapter(ABC):
    """Abstract base class for LLM provider adapters."""

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """An async generator that yields Server-Sent Events for an LLM response."""
        yield

class OpenAIAdapter(BaseLLMAdapter):
    """Adapter for OpenAI-compatible models."""
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._redis_url_signature: Optional[str] = None

    def _ensure_redis_client(self) -> Optional[redis.Redis]:
        redis_url = get_effective_redis_url()
        if not redis_url:
            if self.redis_client:
                try:
                    self.redis_client.close()
                except RedisError:
                    pass
            self.redis_client = None
            self._redis_url_signature = None
            return None

        if self.redis_client is None or self._redis_url_signature != redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                self._redis_url_signature = redis_url
            except RedisError as redis_error:
                logger.warning(
                    "Failed to connect to Redis at %s: %s. Falling back to no-op cache.",
                    redis_url,
                    redis_error,
                )
                self.redis_client = None
                self._redis_url_signature = None

        return self.redis_client

    async def generate_stream(
        self,
        message_id: str, # Added for cancellation checking
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        start_time = time.time()
        was_successful = False
        cancellation_key = f"cancel:stream:{message_id}"

        if openai_client is None:
            logger.debug("OpenAI client unavailable; returning mocked streaming response.")
            await asyncio.sleep(0)
            yield SSEEvent(event="delta", data=SSEDelta(content="[mocked-openai-response]"))
            yield SSEEvent(event="done", data={})
            return

        try:
            redis_client = self._ensure_redis_client()
            stream = await openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice="auto" if tools else None,
                stream=True,
            )

            tool_calls: List[Any] = []
            async for chunk in stream:
                if redis_client and redis_client.exists(cancellation_key):
                    logger.info(f"Cancellation detected for stream {message_id}. Stopping.")
                    redis_client.delete(cancellation_key)  # Clean up the key
                    break

                chunk: ChatCompletionChunk
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield SSEEvent(event="delta", data=SSEDelta(content=delta.content))

                if delta and delta.tool_calls:
                    for tool_call_chunk in delta.tool_calls:
                        if tool_call_chunk.id:
                            tool_calls.append({"id": tool_call_chunk.id, "type": "function", "function": {"name": "", "arguments": ""}})
                        tc = tool_calls[tool_call_chunk.index]["function"]
                        if tool_call_chunk.function:
                            if tool_call_chunk.function.name:
                                tc["name"] += tool_call_chunk.function.name
                            if tool_call_chunk.function.arguments:
                                tc["arguments"] += tool_call_chunk.function.arguments

                if chunk.choices[0].finish_reason == "tool_calls":
                    for tc in tool_calls:
                        yield SSEEvent(event="tool_call", data=SSEToolCall(id=tc["id"], name=tc["function"]["name"], arguments=tc["function"]["arguments"]))

                if chunk.usage:
                    prompt_cost = (chunk.usage.prompt_tokens / 1_000_000) * 5.0
                    completion_cost = (chunk.usage.completion_tokens / 1_000_000) * 15.0
                    total_cost = prompt_cost + completion_cost

                    LLM_TOKENS_TOTAL.labels(provider="openai", kind="prompt").inc(chunk.usage.prompt_tokens)
                    LLM_TOKENS_TOTAL.labels(provider="openai", kind="completion").inc(chunk.usage.completion_tokens)
                    CONVO_COST_USD_TOTAL.inc(total_cost)

                    yield SSEEvent(
                        event="usage",
                        data=SSEUsage(
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens,
                            cost_usd=total_cost,
                        )
                    )
            was_successful = True
        except Exception as e:
            LLM_CALLS_TOTAL.labels(provider="openai", outcome="failure").inc()
            logger.error(f"OpenAI streaming error: {e}", exc_info=True)
            error_data = {"code": e.__class__.__name__, "message": str(e)}
            yield SSEEvent(event="error", data=error_data)

        finally:
            duration = time.time() - start_time
            LLM_LATENCY_SECONDS.labels(provider="openai").observe(duration)
            if was_successful:
                LLM_CALLS_TOTAL.labels(provider="openai", outcome="success").inc()

        yield SSEEvent(event="done", data={})

class AnthropicAdapter(BaseLLMAdapter):
    async def generate_stream(self, messages: List[Dict[str, Any]], model: str, temperature: float, max_tokens: int, tools: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[SSEEvent, None]:
        logger.warning("AnthropicAdapter is not fully implemented yet.")
        yield SSEEvent(event="delta", data=SSEDelta(content="[Anthropic Response Placeholder]"))
        await asyncio.sleep(0.1)
        yield SSEEvent(event="done", data={})

class GoogleAdapter(BaseLLMAdapter):
    async def generate_stream(
        self,
        message_id: str,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        start_time = time.time()
        was_successful = False

        # TODO: Implement Redis-based cancellation check for Gemini streams.

        gemini_model = GenerativeModel(model)

        system_instruction = None
        gemini_messages = []
        for msg in messages:
            if msg["role"] == "system":
                # The system instruction is handled by a dedicated parameter.
                system_instruction = msg["content"]
                continue

            # Gemini uses 'model' for the assistant's role.
            role = "model" if msg["role"] == "assistant" else msg["role"]
            gemini_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

        generation_config = genai_types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        try:
            # NOTE: Assuming `generate_content_async` is the correct method for async streaming
            # based on library conventions, as direct documentation was ambiguous.
            # The `stream=True` parameter is crucial.
            response = await gemini_model.generate_content_async(
                contents=gemini_messages,
                generation_config=generation_config,
                system_instruction=system_instruction,
                stream=True
            )

            async for chunk in response:
                if chunk.text:
                    yield SSEEvent(event="delta", data=SSEDelta(content=chunk.text))

            # TODO: Determine how to get token usage from the Gemini stream.
            # This information does not appear to be in the standard stream chunks.

            was_successful = True
        except AttributeError:
            logger.error(
                "`generate_content_async` not found. The `google-generativeai` library may be outdated or lacks an async client."
            )
            yield SSEEvent(event="error", data={"error": "Gemini adapter is misconfigured or library is incompatible."})
            raise
        except Exception as e:
            LLM_CALLS_TOTAL.labels(provider="google", outcome="failure").inc()
            logger.error(f"Google Gemini streaming error: {e}", exc_info=True)
            error_data = {"code": e.__class__.__name__, "message": str(e)}
            yield SSEEvent(event="error", data=error_data)
        finally:
            duration = time.time() - start_time
            LLM_LATENCY_SECONDS.labels(provider="google").observe(duration)
            if was_successful:
                LLM_CALLS_TOTAL.labels(provider="google", outcome="success").inc()

        yield SSEEvent(event="done", data={})

def get_llm_adapter(provider: str) -> BaseLLMAdapter:
    """Factory function to get an LLM adapter based on the provider."""
    # A real implementation would inspect the model name to determine the provider
    if provider.lower() in ["openai", "gpt-4o", "gpt-4-turbo"]:
        return OpenAIAdapter()
    elif provider.lower() in ["anthropic", "claude-3-opus-20240229"]:
        return AnthropicAdapter()
    elif provider.lower() in ["google", "gemini-1.5-pro-latest"]:
        return GoogleAdapter()
    else:
        logger.warning(f"Unknown LLM provider or model '{provider}'. Defaulting to OpenAI.")
        return OpenAIAdapter()
