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


# --- Standard Application Errors ---

class AppError(Exception):
    """Base application error class."""
    def __init__(self, code: str, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_response(self) -> Dict[str, Any]:
        """Returns a dictionary representation for API responses."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }

class NotFoundError(AppError):
    """To be raised when a resource is not found."""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource.capitalize()} with ID '{resource_id}' not found.",
            status_code=404,
            details={"resource": resource, "resource_id": resource_id}
        )

class InvalidRequestError(AppError):
    """To be raised for validation or other bad request errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="INVALID_REQUEST",
            message=message,
            status_code=400,
            details=details
        )

class UnauthorizedError(AppError):
    """To be raised for authentication errors."""
    def __init__(self, message: str = "Authentication required."):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=401
        )

class ForbiddenError(AppError):
    """To be raised for authorization errors."""
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403
        )
