"""
Data Models and Schemas
"""
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """Chat message model"""
    message_id: str
    room_id: str
    user_id: str
    content: str
    timestamp: int
    role: str = "user"


class Room(BaseModel):
    """Chat room model"""
    room_id: str
    name: str
    created_at: int
    updated_at: int
    message_count: int = 0


class Persona(BaseModel):
    """AI persona configuration"""
    name: str
    provider: str = "openai"
    description: Optional[str] = None


class RoundConfig(BaseModel):
    """Review round configuration"""
    round_number: int
    mode: Literal["divergent", "convergent"]
    instruction: str
    panel_personas: List[Persona]


class CreateReviewRequest(BaseModel):
    """Review creation request"""
    topic: str
    rounds: List[RoundConfig]


class ReviewMeta(BaseModel):
    """Review metadata"""
    model_config = ConfigDict(exclude_none=True)
    
    review_id: str
    room_id: str
    topic: str
    status: Literal["in_progress", "completed", "failed"] = "in_progress"
    total_rounds: int
    current_round: int = 0
    created_at: int
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    failed_panels: List[str] = []


class PanelReport(BaseModel):
    """Individual panel analysis report"""
    model_config = ConfigDict(extra='forbid')
    
    prompt_version: str = "1.0"
    model_name: str
    run_id: str
    persona: str
    
    # Analysis content
    summary: str
    key_points: List[str]
    concerns: List[str]
    recommendations: List[str]
    
    # Metadata
    analysis_timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp()))


class ConsolidatedReport(BaseModel):
    """Consolidated analysis report"""
    model_config = ConfigDict(extra='forbid')
    
    # Metadata
    prompt_version: str = "1.0"
    model_name: str
    run_id: str
    
    # Core content
    topic: str
    executive_summary: str
    perspective_summary: Dict[str, Dict[str, str]]
    alternatives: List[str]
    recommendation: Literal["adopt", "hold", "discard"]
    failed_panels: List[str] = []
    
    # Additional fields
    round_summary: Optional[str] = None
    evidence_sources: Optional[List[str]] = None
    round_number: Optional[int] = None
    round_summaries: Optional[List[Dict[str, Any]]] = None


class ReviewEvent(BaseModel):
    """Review progress event"""
    ts: int
    type: str
    review_id: str
    round: Optional[int] = None
    actor: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    role: Optional[str] = None
    content: Optional[str] = None


class SearchResult(BaseModel):
    """External search result"""
    title: str
    link: str
    snippet: str
    source: str


class ExportData(BaseModel):
    """Export data structure"""
    room_id: str
    messages: List[Message]
    reviews: List[Dict[str, Any]]
    export_timestamp: int
    format: Literal["markdown", "json"] = "markdown"

