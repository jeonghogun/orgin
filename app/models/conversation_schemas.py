"""
Pydantic Schemas for the new Conversation feature.
"""
import time
from typing import List, Optional, Literal, Dict, Any, Union

from pydantic import BaseModel, Field

# --- Attachment Schemas ---

class Attachment(BaseModel):
    id: str
    kind: Literal["file", "image", "audio", "video", "url"]
    name: str
    mime: str
    size: int
    url: str
    created_at: int # Unix timestamp

class AttachmentCreate(BaseModel):
    kind: Literal["file", "image", "audio", "video", "url"]
    name: str
    mime: str
    size: int
    url: str

# --- Tool Call Schemas ---

class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: Dict[str, Any] # e.g., {"name": "webSearch", "arguments": '{"query": "..."}'}

# --- Message Meta Schemas ---

class MessageMeta(BaseModel):
    tokens_prompt: Optional[int] = None
    tokens_output: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    parent_id: Optional[str] = Field(default=None, alias='parentId') # For version tree
    attachments: Optional[List[Attachment]] = None
    tool_calls: Optional[List[ToolCall]] = None

# --- Conversation Message Schemas ---

class ConversationMessage(BaseModel):
    id: str
    thread_id: str
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    model: Optional[str] = None
    status: Literal["draft", "complete", "error"]
    created_at: int # Unix timestamp
    meta: Optional[MessageMeta] = None

    class Config:
        from_attributes = True

class ConversationMessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    attachments: Optional[List[AttachmentCreate]] = None

class ConversationMessageUpdate(BaseModel):
    content: str
    model: Optional[str] = None

# --- Conversation Thread Schemas ---

class ConversationThread(BaseModel):
    id: str
    sub_room_id: str
    user_id: str
    title: str
    pinned: bool
    archived: bool
    created_at: int # Unix timestamp
    updated_at: int # Unix timestamp

    class Config:
        from_attributes = True

class ConversationThreadCreate(BaseModel):
    title: str

class ConversationThreadUpdate(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None

# --- API Specific Schemas ---

class CreateMessageRequest(BaseModel):
    content: str
    attachments: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(2048, gt=0)
    system_prompt: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None

# --- SSE Event Schemas ---

class SSEDelta(BaseModel):
    content: str

class SSEToolCall(BaseModel):
    id: str
    name: str
    arguments: str

class SSEUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Optional[float] = None

class SSEEvent(BaseModel):
    event: Literal["delta", "tool_call", "usage", "done", "error"]
    data: Union[SSEDelta, SSEToolCall, SSEUsage, Dict[str, Any]]
