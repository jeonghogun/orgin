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
    owner_id: str
    type: Literal["main", "sub", "review"] = "sub"
    parent_id: Optional[str] = None
    created_at: int
    updated_at: int
    message_count: int = 0


class CreateRoomRequest(BaseModel):
    """Room creation request"""

    name: str
    type: Literal["main", "sub", "review"] = "sub"
    parent_id: Optional[str] = None


class CreateReviewRequest(BaseModel):
    """Review creation request"""

    topic: str
    instruction: str
    panelists: Optional[List[str]] = None


class ReviewMeta(BaseModel):
    """Review metadata"""

    model_config = ConfigDict()

    review_id: str
    room_id: str
    topic: str
    instruction: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    total_rounds: int
    current_round: int = 0
    created_at: int
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    failed_panels: List[str] = []


class ReviewFull(ReviewMeta):
    """Full review data including the final report."""
    final_report: Optional[Dict[str, Any]] = None


class ExportableReview(BaseModel):
    """A structured representation of a review for data export."""
    topic: str
    status: str
    created_at: int
    final_summary: str
    next_steps: List[str]


class PanelReport(BaseModel):
    """Individual panel analysis report"""

    model_config = ConfigDict(extra="forbid")

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
    analysis_timestamp: int = Field(
        default_factory=lambda: int(datetime.now().timestamp())
    )


class ConsolidatedReport(BaseModel):
    """Consolidated analysis report"""

    model_config = ConfigDict(extra="forbid")

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


class WebSocketMessage(BaseModel):
    """Standardized envelope for WebSocket messages."""
    type: str  # e.g., 'status_update', 'error'
    review_id: str
    ts: int = Field(default_factory=lambda: int(time.time()))
    version: str = "1.0"
    payload: Dict[str, Any]


class SearchResult(BaseModel):
    """External search result"""

    title: str
    link: str
    snippet: str
    source: str


class ExportData(BaseModel):
    """Export data structure"""

    room_id: str
    room_name: str
    messages: List[Message]
    reviews: List[ExportableReview]
    export_timestamp: int


class ReviewMetrics(BaseModel):
    """Review metrics model"""

    review_id: str
    total_duration_seconds: float
    total_tokens_used: int
    total_cost_usd: float
    round_metrics: List[List[Dict[str, Any]]]
    provider_metrics: Dict[str, Dict[str, Any]] = {} # e.g. {"openai": {"success": 1, "fail": 0, "total_tokens": 500}}
    created_at: int


class MetricsSummary(BaseModel):
    """Metrics summary model"""

    total_reviews: int
    avg_duration: float
    median_duration: float
    p95_duration: float
    avg_tokens: float
    median_tokens: float
    p95_tokens: float
    provider_summary: Dict[str, Dict[str, Any]] = {}


class MetricsResponse(BaseModel):
    """Metrics API response model"""

    summary: MetricsSummary
    data: List[ReviewMetrics]


class PanelistConfig(BaseModel):
    """Configuration for a panelist in the review system"""
    
    name: str
    provider: str  # openai, gemini, claude
    model: str
    role: Optional[str] = None
    temperature: Optional[float] = 0.7
