"""
Memory and Context Management Schemas
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ConversationContext(BaseModel):
    """대화 맥락 정보"""
    context_id: str = Field(..., description="맥락 ID")
    room_id: str = Field(..., description="방 ID")
    user_id: str = Field(..., description="사용자 ID")
    summary: str = Field(default="", description="대화 요약")
    key_topics: List[str] = Field(default_factory=list, description="주요 주제들")
    sentiment: str = Field(default="neutral", description="감정 상태")
    created_at: int = Field(..., description="생성 시간")
    updated_at: int = Field(..., description="업데이트 시간")


class UserProfile(BaseModel):
    """사용자 프로필 정보"""
    user_id: str = Field(..., description="사용자 ID")
    name: Optional[str] = Field(default=None, description="사용자 이름")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="사용자 선호도")
    conversation_style: str = Field(default="casual", description="대화 스타일")
    interests: List[str] = Field(default_factory=list, description="관심사")
    created_at: int = Field(..., description="생성 시간")
    updated_at: int = Field(..., description="업데이트 시간")


class MemoryEntry(BaseModel):
    """메모리 엔트리"""
    memory_id: str = Field(..., description="메모리 ID")
    room_id: str = Field(..., description="방 ID")
    user_id: str = Field(..., description="사용자 ID")
    key: str = Field(..., description="메모리 키")
    value: str = Field(..., description="메모리 값")
    importance: float = Field(default=1.0, description="중요도 (0.0-1.0)")
    expires_at: Optional[int] = Field(default=None, description="만료 시간")
    created_at: int = Field(..., description="생성 시간")


class ContextQuery(BaseModel):
    """맥락 조회 요청"""
    room_id: str = Field(..., description="방 ID")
    user_id: str = Field(..., description="사용자 ID")
    limit: int = Field(default=10, description="조회할 맥락 수")
    include_memories: bool = Field(default=True, description="메모리 포함 여부")


class ContextUpdate(BaseModel):
    """맥락 업데이트 요청"""
    room_id: str = Field(..., description="방 ID")
    user_id: str = Field(..., description="사용자 ID")
    summary: Optional[str] = Field(default=None, description="새로운 요약")
    key_topics: Optional[List[str]] = Field(default=None, description="새로운 주제들")
    sentiment: Optional[str] = Field(default=None, description="새로운 감정 상태")
    new_memory: Optional[Dict[str, str]] = Field(default=None, description="새로운 메모리")
