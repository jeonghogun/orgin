"""
Background Task Service
백그라운드 작업의 안정성과 재시도 로직을 관리
"""
import logging
import asyncio
from typing import Callable, Any, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import traceback

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"

@dataclass
class TaskResult:
    status: TaskStatus
    result: Any = None
    error: Optional[Exception] = None
    retry_count: int = 0
    execution_time: float = 0.0

class BackgroundTaskService:
    """백그라운드 작업 관리 서비스"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.task_results: Dict[str, TaskResult] = {}

    async def execute_with_retry(
        self, 
        task_id: str,
        coro_func: Callable,
        *args,
        **kwargs
    ) -> TaskResult:
        """
        재시도 로직이 포함된 백그라운드 작업 실행
        
        Args:
            task_id: 작업 고유 ID
            coro_func: 실행할 코루틴 함수
            *args, **kwargs: 함수에 전달할 인자들
        """
        import time
        start_time = time.time()
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"Executing background task {task_id}, attempt {attempt + 1}/{self.max_retries + 1}")
                
                # 작업 상태 업데이트
                if attempt > 0:
                    self.task_results[task_id] = TaskResult(
                        status=TaskStatus.RETRYING,
                        retry_count=attempt
                    )
                else:
                    self.task_results[task_id] = TaskResult(
                        status=TaskStatus.RUNNING,
                        retry_count=attempt
                    )
                
                # 작업 실행
                result = await coro_func(*args, **kwargs)
                
                # 성공
                execution_time = time.time() - start_time
                self.task_results[task_id] = TaskResult(
                    status=TaskStatus.SUCCESS,
                    result=result,
                    retry_count=attempt,
                    execution_time=execution_time
                )
                
                logger.info(f"Background task {task_id} completed successfully in {execution_time:.2f}s")
                return self.task_results[task_id]
                
            except Exception as e:
                execution_time = time.time() - start_time
                error_msg = f"Background task {task_id} failed on attempt {attempt + 1}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # 마지막 시도가 아니면 재시도
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    logger.info(f"Retrying task {task_id} in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # 최대 재시도 횟수 초과
                    self.task_results[task_id] = TaskResult(
                        status=TaskStatus.MAX_RETRIES_EXCEEDED,
                        error=e,
                        retry_count=attempt,
                        execution_time=execution_time
                    )
                    
                    # 에러 로깅 (Sentry 등에 전송 가능)
                    await self._log_error(task_id, e, execution_time)
                    
                    logger.error(f"Background task {task_id} failed after {self.max_retries + 1} attempts")
                    return self.task_results[task_id]

    async def _log_error(self, task_id: str, error: Exception, execution_time: float):
        """에러 로깅 (Sentry 등 확장 가능)"""
        error_details = {
            "task_id": task_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "execution_time": execution_time,
            "traceback": traceback.format_exc()
        }
        
        # 현재는 로그로만 출력, 나중에 Sentry 등으로 확장 가능
        logger.error(f"Background task error details: {error_details}")
        
        # TODO: Sentry나 다른 에러 추적 서비스로 전송
        # await self._send_to_sentry(error_details)

    def create_background_task(
        self, 
        task_id: str,
        coro_func: Callable,
        *args,
        **kwargs
    ) -> asyncio.Task:
        """
        백그라운드 작업을 생성하고 실행
        
        Returns:
            asyncio.Task: 생성된 작업 객체
        """
        async def wrapper():
            return await self.execute_with_retry(task_id, coro_func, *args, **kwargs)
        
        task = asyncio.create_task(wrapper())
        self.running_tasks[task_id] = task
        
        # 작업 완료 시 정리
        task.add_done_callback(lambda t: self.running_tasks.pop(task_id, None))
        
        logger.info(f"Created background task {task_id}")
        return task

    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """작업 상태 조회"""
        return self.task_results.get(task_id)

    def get_running_tasks(self) -> Dict[str, asyncio.Task]:
        """실행 중인 작업 목록"""
        return self.running_tasks.copy()

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> TaskResult:
        """작업 완료 대기"""
        if task_id not in self.running_tasks:
            return self.task_results.get(task_id, TaskResult(TaskStatus.FAILED))
        
        try:
            await asyncio.wait_for(self.running_tasks[task_id], timeout=timeout)
            return self.task_results.get(task_id, TaskResult(TaskStatus.FAILED))
        except asyncio.TimeoutError:
            logger.warning(f"Task {task_id} timed out after {timeout}s")
            return TaskResult(TaskStatus.FAILED)

    async def cancel_task(self, task_id: str) -> bool:
        """작업 취소"""
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            logger.info(f"Cancelled background task {task_id}")
            return True
        return False

    async def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """완료된 작업 결과 정리"""
        import time
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        to_remove = []
        for task_id, result in self.task_results.items():
            if (result.status in [TaskStatus.SUCCESS, TaskStatus.MAX_RETRIES_EXCEEDED] and 
                current_time - result.execution_time > max_age_seconds):
                to_remove.append(task_id)
        
        for task_id in to_remove:
            self.task_results.pop(task_id, None)
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} completed task results")
