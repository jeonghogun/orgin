"""
LLM Service Error Definitions
"""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class LLMErrorCode(Enum):
    """LLM 서비스 에러 코드"""
    
    # API 관련 에러
    RATE_LIMIT = "rate_limit"
    API_ERROR = "api_error"
    TIMEOUT = "timeout"
    
    # 인증/권한 에러
    AUTH_FAILED = "auth_failed"
    INSUFFICIENT_QUOTA = "insufficient_quota"
    
    # 요청 관련 에러
    INVALID_REQUEST = "invalid_request"
    CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
    MODEL_NOT_FOUND = "model_not_found"
    
    # 네트워크 에러
    NETWORK_ERROR = "network_error"
    CONNECTION_ERROR = "connection_error"
    
    # 내부 에러
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class LLMError(Exception):
    """LLM 서비스 내부 에러"""
    
    error_code: LLMErrorCode
    provider: str
    retryable: bool
    original_error: Optional[Exception] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.error_message is None:
            self.error_message = f"LLM Error: {self.error_code.value} from {self.provider}"
        super().__init__(self.error_message)
    
    def to_dict(self) -> Dict[str, Any]:
        """에러를 딕셔너리로 변환 (로깅용)"""
        return {
            "error_code": self.error_code.value,
            "provider": self.provider,
            "retryable": self.retryable,
            "error_message": self.error_message,
            "original_error": str(self.original_error) if self.original_error else None,
            "metadata": self.metadata or {}
        }


def should_retry_error(error: LLMError) -> bool:
    """에러가 재시도 가능한지 확인"""
    return error.retryable


def get_retry_delay(retry_count: int, base_delay: float = 1.0) -> float:
    """지수 백오프 + 지터 계산"""
    import random
    
    # 지수 백오프: 1s, 2s, 4s, 8s, 16s...
    exponential_delay = base_delay * (2 ** retry_count)
    
    # 지터 추가 (±25%)
    jitter = exponential_delay * 0.25 * random.uniform(-1, 1)
    
    # 최대 60초 제한
    return min(exponential_delay + jitter, 60.0)
