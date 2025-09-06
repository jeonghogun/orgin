import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional

import openai
from anthropic import AsyncAnthropic
from google.generativeai import GenerativeModel, configure
from openai.types.chat import ChatCompletionChunk

import redis
from app.config.settings import settings
from app.models.conversation_schemas import SSEEvent, SSEDelta, SSEToolCall, SSEUsage
from app.core.metrics import LLM_CALLS_TOTAL, LLM_LATENCY_SECONDS, LLM_TOKENS_TOTAL, CONVO_COST_USD_TOTAL

logger = logging.getLogger(__name__)

# Configure clients at module level
openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
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
        self.redis_client = redis.from_url(settings.REDIS_URL)

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

        try:
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
                if self.redis_client.exists(cancellation_key):
                    logger.info(f"Cancellation detected for stream {message_id}. Stopping.")
                    self.redis_client.delete(cancellation_key) # Clean up the key
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
    async def generate_stream(self, messages: List[Dict[str, Any]], model: str, temperature: float, max_tokens: int, tools: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[SSEEvent, None]:
        logger.warning("GoogleAdapter is not fully implemented yet.")
        yield SSEEvent(event="delta", data=SSEDelta(content="[Google Gemini Response Placeholder]"))
        await asyncio.sleep(0.1)
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
