"""
LLM Provider Error Mapping
"""

import asyncio
from typing import Optional, Dict, Any
import openai
import anthropic
import google.generativeai as genai

# aiohttp를 선택적으로 import
try:
    from aiohttp import ClientError, ClientTimeout
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    # aiohttp가 없을 때 사용할 대체 클래스들
    class ClientError(Exception):
        pass
    
    class ClientTimeout:
        pass

from app.core.errors import LLMError, LLMErrorCode


def map_openai_error(error: Exception, provider: str = "openai") -> LLMError:
    """OpenAI API 에러를 내부 LLMError로 매핑"""
    
    if isinstance(error, openai.RateLimitError):
        return LLMError(
            error_code=LLMErrorCode.RATE_LIMIT,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"OpenAI rate limit exceeded: {error.message}",
            metadata={"retry_after": getattr(error, 'retry_after', None)}
        )
    
    elif isinstance(error, openai.AuthenticationError):
        return LLMError(
            error_code=LLMErrorCode.AUTH_FAILED,
            provider=provider,
            retryable=False,
            original_error=error,
            error_message=f"OpenAI authentication failed: {error.message}"
        )
    
    elif isinstance(error, openai.InvalidRequestError):
        # 토큰 초과인지 확인
        if "context_length_exceeded" in str(error).lower():
            return LLMError(
                error_code=LLMErrorCode.CONTEXT_LENGTH_EXCEEDED,
                provider=provider,
                retryable=False,
                original_error=error,
                error_message=f"OpenAI context length exceeded: {error.message}"
            )
        else:
            return LLMError(
                error_code=LLMErrorCode.INVALID_REQUEST,
                provider=provider,
                retryable=False,
                original_error=error,
                error_message=f"OpenAI invalid request: {error.message}"
            )
    
    elif isinstance(error, openai.APIError):
        return LLMError(
            error_code=LLMErrorCode.API_ERROR,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"OpenAI API error: {error.message}"
        )
    
    elif isinstance(error, asyncio.TimeoutError):
        return LLMError(
            error_code=LLMErrorCode.TIMEOUT,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"OpenAI request timeout"
        )
    
    elif isinstance(error, (ClientError, ConnectionError)):
        return LLMError(
            error_code=LLMErrorCode.NETWORK_ERROR,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"OpenAI network error: {str(error)}"
        )
    
    else:
        return LLMError(
            error_code=LLMErrorCode.UNKNOWN_ERROR,
            provider=provider,
            retryable=False,
            original_error=error,
            error_message=f"OpenAI unknown error: {str(error)}"
        )


def map_anthropic_error(error: Exception, provider: str = "claude") -> LLMError:
    """Anthropic API 에러를 내부 LLMError로 매핑"""
    
    if isinstance(error, anthropic.RateLimitError):
        return LLMError(
            error_code=LLMErrorCode.RATE_LIMIT,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"Anthropic rate limit exceeded: {error.message}",
            metadata={"retry_after": getattr(error, 'retry_after', None)}
        )
    
    elif isinstance(error, anthropic.AuthenticationError):
        return LLMError(
            error_code=LLMErrorCode.AUTH_FAILED,
            provider=provider,
            retryable=False,
            original_error=error,
            error_message=f"Anthropic authentication failed: {error.message}"
        )
    
    elif isinstance(error, anthropic.BadRequestError):
        if "context_length" in str(error).lower():
            return LLMError(
                error_code=LLMErrorCode.CONTEXT_LENGTH_EXCEEDED,
                provider=provider,
                retryable=False,
                original_error=error,
                error_message=f"Anthropic context length exceeded: {error.message}"
            )
        else:
            return LLMError(
                error_code=LLMErrorCode.INVALID_REQUEST,
                provider=provider,
                retryable=False,
                original_error=error,
                error_message=f"Anthropic invalid request: {error.message}"
            )
    
    elif isinstance(error, anthropic.APIError):
        return LLMError(
            error_code=LLMErrorCode.API_ERROR,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"Anthropic API error: {error.message}"
        )
    
    elif isinstance(error, asyncio.TimeoutError):
        return LLMError(
            error_code=LLMErrorCode.TIMEOUT,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"Anthropic request timeout"
        )
    
    elif isinstance(error, (ClientError, ConnectionError)):
        return LLMError(
            error_code=LLMErrorCode.NETWORK_ERROR,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"Anthropic network error: {str(error)}"
        )
    
    else:
        return LLMError(
            error_code=LLMErrorCode.UNKNOWN_ERROR,
            provider=provider,
            retryable=False,
            original_error=error,
            error_message=f"Anthropic unknown error: {str(error)}"
        )


def map_gemini_error(error: Exception, provider: str = "gemini") -> LLMError:
    """Google Gemini API 에러를 내부 LLMError로 매핑"""
    
    # Gemini는 Google의 예외를 사용
    if hasattr(error, 'status_code'):
        if error.status_code == 429:  # Rate limit
            return LLMError(
                error_code=LLMErrorCode.RATE_LIMIT,
                provider=provider,
                retryable=True,
                original_error=error,
                error_message=f"Gemini rate limit exceeded: {str(error)}"
            )
        elif error.status_code == 401:  # Auth failed
            return LLMError(
                error_code=LLMErrorCode.AUTH_FAILED,
                provider=provider,
                retryable=False,
                original_error=error,
                error_message=f"Gemini authentication failed: {str(error)}"
            )
        elif error.status_code == 400:  # Bad request
            if "context_length" in str(error).lower():
                return LLMError(
                    error_code=LLMErrorCode.CONTEXT_LENGTH_EXCEEDED,
                    provider=provider,
                    retryable=False,
                    original_error=error,
                    error_message=f"Gemini context length exceeded: {str(error)}"
                )
            else:
                return LLMError(
                    error_code=LLMErrorCode.INVALID_REQUEST,
                    provider=provider,
                    retryable=False,
                    original_error=error,
                    error_message=f"Gemini invalid request: {str(error)}"
                )
        else:
            return LLMError(
                error_code=LLMErrorCode.API_ERROR,
                provider=provider,
                retryable=True,
                original_error=error,
                error_message=f"Gemini API error: {str(error)}"
            )
    
    elif isinstance(error, asyncio.TimeoutError):
        return LLMError(
            error_code=LLMErrorCode.TIMEOUT,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"Gemini request timeout"
        )
    
    elif isinstance(error, (ClientError, ConnectionError)):
        return LLMError(
            error_code=LLMErrorCode.NETWORK_ERROR,
            provider=provider,
            retryable=True,
            original_error=error,
            error_message=f"Gemini network error: {str(error)}"
        )
    
    else:
        return LLMError(
            error_code=LLMErrorCode.UNKNOWN_ERROR,
            provider=provider,
            retryable=False,
            original_error=error,
            error_message=f"Gemini unknown error: {str(error)}"
        )
