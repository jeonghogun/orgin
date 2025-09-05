"""
Performance Monitoring and APM Integration
"""

import logging
import time
import functools
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager

from app.config.settings import settings

logger = logging.getLogger(__name__)

# New Relic APM
try:
    import newrelic.agent
    NEW_RELIC_AVAILABLE = True
except ImportError:
    NEW_RELIC_AVAILABLE = False
    logger.warning("New Relic not available. Install with: pip install newrelic")

# DataDog APM
try:
    from ddtrace import tracer
    DATADOG_AVAILABLE = True
except ImportError:
    DATADOG_AVAILABLE = False
    logger.warning("DataDog not available. Install with: pip install ddtrace")


class PerformanceMonitor:
    """성능 모니터링 클래스"""
    
    def __init__(self):
        self.enabled = settings.ENABLE_METRICS
        self.tracing_enabled = settings.ENABLE_TRACING
        self.alerts_enabled = settings.ENABLE_ALERTS
        
        # New Relic 초기화
        if NEW_RELIC_AVAILABLE and settings.NEW_RELIC_LICENSE_KEY:
            newrelic.agent.initialize(
                settings.NEW_RELIC_LICENSE_KEY,
                settings.NEW_RELIC_APP_NAME
            )
            logger.info("New Relic APM initialized")
        
        # DataDog 초기화
        if DATADOG_AVAILABLE and settings.DATADOG_API_KEY:
            tracer.configure(
                service=settings.DATADOG_SERVICE,
                api_key=settings.DATADOG_API_KEY
            )
            logger.info("DataDog APM initialized")
    
    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """메트릭 기록"""
        if not self.enabled:
            return
        
        try:
            if NEW_RELIC_AVAILABLE:
                newrelic.agent.record_custom_metric(name, value)
            
            if DATADOG_AVAILABLE:
                from ddtrace import tracer
                with tracer.trace(name) as span:
                    span.set_tag("value", value)
                    if tags:
                        for key, val in tags.items():
                            span.set_tag(key, val)
            
            logger.debug(f"Metric recorded: {name}={value}, tags={tags}")
        except Exception as e:
            logger.error(f"Failed to record metric {name}: {e}")
    
    def record_timing(self, name: str, duration: float, tags: Optional[Dict[str, str]] = None):
        """타이밍 메트릭 기록"""
        self.record_metric(f"Custom/{name}/Duration", duration, tags)
    
    def record_count(self, name: str, count: int = 1, tags: Optional[Dict[str, str]] = None):
        """카운트 메트릭 기록"""
        self.record_metric(f"Custom/{name}/Count", count, tags)
    
    def record_error(self, error_type: str, error_message: str, tags: Optional[Dict[str, str]] = None):
        """에러 메트릭 기록"""
        error_tags = {"error_type": error_type, "error_message": error_message}
        if tags:
            error_tags.update(tags)
        
        self.record_count("Errors", 1, error_tags)
        
        # New Relic 에러 기록
        if NEW_RELIC_AVAILABLE:
            newrelic.agent.record_exception()
    
    @contextmanager
    def trace_operation(self, operation_name: str, tags: Optional[Dict[str, str]] = None):
        """작업 추적 컨텍스트 매니저"""
        if not self.tracing_enabled:
            yield
            return
        
        start_time = time.time()
        operation_tags = tags or {}
        
        try:
            # New Relic 트랜잭션 시작
            if NEW_RELIC_AVAILABLE:
                newrelic.agent.add_custom_parameter("operation", operation_name)
                for key, value in operation_tags.items():
                    newrelic.agent.add_custom_parameter(key, value)
            
            # DataDog 스팬 시작
            if DATADOG_AVAILABLE:
                with tracer.trace(operation_name) as span:
                    for key, value in operation_tags.items():
                        span.set_tag(key, value)
                    yield span
            else:
                yield None
                
        except Exception as e:
            self.record_error(type(e).__name__, str(e), operation_tags)
            raise
        finally:
            duration = time.time() - start_time
            self.record_timing(operation_name, duration, operation_tags)
    
    def monitor_function(self, operation_name: Optional[str] = None, tags: Optional[Dict[str, str]] = None):
        """함수 모니터링 데코레이터"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                name = operation_name or f"{func.__module__}.{func.__name__}"
                with self.trace_operation(name, tags):
                    return await func(*args, **kwargs)
            
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                name = operation_name or f"{func.__module__}.{func.__name__}"
                with self.trace_operation(name, tags):
                    return func(*args, **kwargs)
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator


# 전역 모니터링 인스턴스
performance_monitor = PerformanceMonitor()


def monitor_operation(operation_name: Optional[str] = None, tags: Optional[Dict[str, str]] = None):
    """작업 모니터링 데코레이터"""
    return performance_monitor.monitor_function(operation_name, tags)


def record_metric(name: str, value: float, tags: Optional[Dict[str, str]] = None):
    """메트릭 기록 헬퍼 함수"""
    performance_monitor.record_metric(name, value, tags)


def record_timing(name: str, duration: float, tags: Optional[Dict[str, str]] = None):
    """타이밍 메트릭 기록 헬퍼 함수"""
    performance_monitor.record_timing(name, duration, tags)


def record_error(error_type: str, error_message: str, tags: Optional[Dict[str, str]] = None):
    """에러 메트릭 기록 헬퍼 함수"""
    performance_monitor.record_error(error_type, error_message, tags)
