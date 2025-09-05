"""
Real-time Alert System
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

import aiohttp
from app.config.settings import settings

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """알림 심각도"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """알림 데이터 클래스"""
    title: str
    message: str
    severity: AlertSeverity
    source: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, str]] = None


class AlertRule:
    """알림 규칙"""
    
    def __init__(
        self,
        name: str,
        condition: Callable[[Dict[str, Any]], bool],
        severity: AlertSeverity,
        cooldown_minutes: int = 5
    ):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.cooldown_minutes = cooldown_minutes
        self.last_triggered: Optional[datetime] = None
    
    def should_trigger(self, data: Dict[str, Any]) -> bool:
        """알림을 트리거해야 하는지 확인"""
        if not self.condition(data):
            return False
        
        # 쿨다운 확인
        if self.last_triggered:
            cooldown_end = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
            if datetime.now() < cooldown_end:
                return False
        
        self.last_triggered = datetime.now()
        return True


class AlertManager:
    """알림 관리자"""
    
    def __init__(self):
        self.rules: List[AlertRule] = []
        self.handlers: List[Callable[[Alert], None]] = []
        self.webhook_url = settings.ALERT_WEBHOOK_URL
        self.enabled = settings.ENABLE_ALERTS
        
        # 기본 알림 규칙 설정
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """기본 알림 규칙 설정"""
        
        # 에러율 임계값 규칙
        self.add_rule(
            AlertRule(
                name="high_error_rate",
                condition=lambda data: data.get("error_rate", 0) > 0.05,  # 5% 이상
                severity=AlertSeverity.WARNING,
                cooldown_minutes=10
            )
        )
        
        # 응답 시간 임계값 규칙
        self.add_rule(
            AlertRule(
                name="high_response_time",
                condition=lambda data: data.get("avg_response_time", 0) > 5.0,  # 5초 이상
                severity=AlertSeverity.WARNING,
                cooldown_minutes=5
            )
        )
        
        # API 키 만료 임박 규칙
        self.add_rule(
            AlertRule(
                name="api_key_expiring",
                condition=lambda data: data.get("api_key_expires_in", 999999) < 86400,  # 24시간 이내
                severity=AlertSeverity.ERROR,
                cooldown_minutes=60
            )
        )
        
        # 데이터베이스 연결 실패 규칙
        self.add_rule(
            AlertRule(
                name="database_connection_failed",
                condition=lambda data: data.get("db_connection_status") == "failed",
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=2
            )
        )
        
        # 메모리 사용량 임계값 규칙
        self.add_rule(
            AlertRule(
                name="high_memory_usage",
                condition=lambda data: data.get("memory_usage_percent", 0) > 80,  # 80% 이상
                severity=AlertSeverity.WARNING,
                cooldown_minutes=15
            )
        )
    
    def add_rule(self, rule: AlertRule):
        """알림 규칙 추가"""
        self.rules.append(rule)
        logger.info(f"Alert rule added: {rule.name}")
    
    def add_handler(self, handler: Callable[[Alert], None]):
        """알림 핸들러 추가"""
        self.handlers.append(handler)
        logger.info(f"Alert handler added: {handler.__name__}")
    
    async def check_alerts(self, data: Dict[str, Any]):
        """알림 조건 확인"""
        if not self.enabled:
            return
        
        for rule in self.rules:
            if rule.should_trigger(data):
                alert = Alert(
                    title=f"Alert: {rule.name}",
                    message=f"Condition triggered for {rule.name}",
                    severity=rule.severity,
                    source="system",
                    timestamp=datetime.now(),
                    metadata=data,
                    tags={"rule": rule.name}
                )
                
                await self.send_alert(alert)
    
    async def send_alert(self, alert: Alert):
        """알림 전송"""
        logger.warning(f"Alert triggered: {alert.title} - {alert.message}")
        
        # 핸들러 실행
        for handler in self.handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
        
        # 웹훅 전송
        if self.webhook_url:
            await self._send_webhook(alert)
    
    async def _send_webhook(self, alert: Alert):
        """웹훅으로 알림 전송"""
        try:
            payload = {
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity.value,
                "source": alert.source,
                "timestamp": alert.timestamp.isoformat(),
                "metadata": alert.metadata,
                "tags": alert.tags
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status >= 400:
                        logger.error(f"Webhook failed: {response.status}")
                    else:
                        logger.info("Alert sent via webhook")
                        
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
    
    def create_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        source: str = "manual",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> Alert:
        """수동 알림 생성"""
        return Alert(
            title=title,
            message=message,
            severity=severity,
            source=source,
            timestamp=datetime.now(),
            metadata=metadata,
            tags=tags
        )
    
    async def send_manual_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.INFO,
        source: str = "manual",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None
    ):
        """수동 알림 전송"""
        alert = self.create_alert(title, message, severity, source, metadata, tags)
        await self.send_alert(alert)


# 전역 알림 관리자 인스턴스
alert_manager = AlertManager()


# 편의 함수들
async def send_alert(
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.INFO,
    source: str = "manual",
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[Dict[str, str]] = None
):
    """알림 전송 헬퍼 함수"""
    await alert_manager.send_manual_alert(title, message, severity, source, metadata, tags)


def check_alerts(data: Dict[str, Any]):
    """알림 조건 확인 헬퍼 함수"""
    asyncio.create_task(alert_manager.check_alerts(data))
