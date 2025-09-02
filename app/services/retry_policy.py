"""
LLM Service Retry Policy and Circuit Breaker
"""

import asyncio
import time
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from collections import deque

from app.core.errors import LLMError, should_retry_error, get_retry_delay


@dataclass
class RetryConfig:
    """재시도 설정"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.25


class CircuitBreaker:
    """회로차단기 - 연속 실패 시 일시적으로 차단"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def record_failure(self):
        """실패 기록"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
    
    def record_success(self):
        """성공 기록"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def can_execute(self) -> bool:
        """실행 가능한지 확인"""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            # 복구 시간이 지났으면 HALF_OPEN으로 전환
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        
        # HALF_OPEN 상태에서는 한 번만 시도
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """상태 정보 반환"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "can_execute": self.can_execute()
        }


class LLMRetryManager:
    """LLM 서비스 재시도 관리자"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.retry_config = RetryConfig()
    
    def get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """프로바이더별 회로차단기 가져오기"""
        if provider not in self.circuit_breakers:
            self.circuit_breakers[provider] = CircuitBreaker()
        return self.circuit_breakers[provider]
    
    async def execute_with_retry(
        self,
        func: Callable,
        provider: str,
        *args,
        **kwargs
    ) -> Any:
        """재시도 로직으로 함수 실행"""
        
        circuit_breaker = self.get_circuit_breaker(provider)
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # 회로차단기 확인
                if not circuit_breaker.can_execute():
                    raise LLMError(
                        error_code="PROVIDER_UNAVAILABLE",
                        provider=provider,
                        retryable=False,
                        error_message=f"Circuit breaker is OPEN for {provider}"
                    )
                
                # 함수 실행
                result = await func(*args, **kwargs)
                
                # 성공 시 회로차단기 리셋
                circuit_breaker.record_success()
                return result
                
            except LLMError as e:
                # 재시도 가능한 에러인지 확인
                if not should_retry_error(e) or attempt >= self.retry_config.max_retries:
                    circuit_breaker.record_failure()
                    raise e
                
                # 재시도 대기
                delay = get_retry_delay(attempt, self.retry_config.base_delay)
                await asyncio.sleep(delay)
                
            except Exception as e:
                # 알 수 없는 에러는 재시도하지 않음
                circuit_breaker.record_failure()
                raise LLMError(
                    error_code="UNKNOWN_ERROR",
                    provider=provider,
                    retryable=False,
                    original_error=e,
                    error_message=f"Unknown error: {str(e)}"
                )
    
    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """모든 프로바이더 상태 반환"""
        return {
            provider: circuit_breaker.get_status()
            for provider, circuit_breaker in self.circuit_breakers.items()
        }


    def execute_with_retry_sync(
        self,
        func: Callable,
        provider: str,
        *args,
        **kwargs
    ) -> Any:
        """재시도 로직으로 함수를 동기적으로 실행"""

        circuit_breaker = self.get_circuit_breaker(provider)

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                if not circuit_breaker.can_execute():
                    raise LLMError(
                        error_code="PROVIDER_UNAVAILABLE",
                        provider=provider,
                        retryable=False,
                        error_message=f"Circuit breaker is OPEN for {provider}"
                    )

                result = func(*args, **kwargs) # No await

                circuit_breaker.record_success()
                return result

            except LLMError as e:
                if not should_retry_error(e) or attempt >= self.retry_config.max_retries:
                    circuit_breaker.record_failure()
                    raise e

                delay = get_retry_delay(attempt, self.retry_config.base_delay)
                time.sleep(delay) # Use time.sleep

            except Exception as e:
                circuit_breaker.record_failure()
                raise LLMError(
                    error_code="UNKNOWN_ERROR",
                    provider=provider,
                    retryable=False,
                    original_error=e,
                    error_message=f"Unknown error: {str(e)}"
                )

# 전역 재시도 관리자 인스턴스
retry_manager = LLMRetryManager()
