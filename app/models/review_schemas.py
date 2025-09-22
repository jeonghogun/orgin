"""Pydantic models for validating the structured JSON output from LLMs.

The new conversation-oriented format keeps the multi-round structure but expects
each panelist turn to look like a real chat bubble with explicit cross
references.  Downstream code still relies on structured fields to build light
weight digests for subsequent prompts, so the schema keeps a concise
``key_takeaway`` in addition to the natural language ``message``.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ConversationReference(BaseModel):
    """Reference to another panelist's earlier contribution."""

    panelist: str = Field(..., description="Name of the panelist being referenced.")
    round: int = Field(..., ge=1, description="Round number for the referenced remark.")
    quote: str = Field(..., description="Short quote or paraphrase being referenced.")
    stance: Literal["support", "challenge", "build", "clarify"] = Field(
        ..., description="How the speaker is using the reference."
    )


class LLMReviewTurn(BaseModel):
    """Unified schema for every conversational turn across rounds."""

    round: int = Field(..., ge=1, description="Current round number.")
    panelist: str = Field(..., description="Panelist delivering the message.")
    message: str = Field(
        ..., description="Natural language chat bubble styled for the live debate."
    )
    key_takeaway: str = Field(
        ..., description="One-line digest reused when prompting future rounds."
    )
    references: List[ConversationReference] = Field(
        default_factory=list,
        description="Cross references to other panelists' remarks.",
    )
    no_new_arguments: bool = Field(
        default=False,
        description="True if the panelist has nothing substantive to add this round.",
    )


class LLMReviewResolution(BaseModel):
    """Structured payload for the final alignment round."""

    round: Literal[4] = Field(..., description="Round number fixed at 4 for final alignment.")
    panelist: Optional[str] = Field(
        default=None,
        description="Panelist delivering the final alignment message.",
    )
    final_position: str = Field(
        ..., description="The panelist's final recommendation or stance."
    )
    consensus_highlights: List[str] = Field(
        default_factory=list,
        description="Strong consensus items to emphasise.",
    )
    open_questions: List[str] = Field(
        default_factory=list,
        description="Remaining disagreements or risks.",
    )
    next_steps: List[str] = Field(
        default_factory=list,
        description="Concrete follow-up actions.",
    )
    no_new_arguments: bool = Field(
        default=False,
        description="True when the panelist has nothing to add beyond prior rounds.",
    )

class LLMFinalReport(BaseModel):
    """
    Expected JSON structure for the final consolidated report.
    """
    executive_summary: str = Field(..., description="The final summary, including key insights from the entire discussion.")
    strongest_consensus: List[str] = Field(..., description="Key points that panelists commonly agreed on.")
    remaining_disagreements: List[str] = Field(..., description="Significant disagreements that remained, if any.")
    recommendations: List[str] = Field(..., description="A list of consolidated final recommendations.")


class LLMReviewTopicSuggestion(BaseModel):
    """Structured response for an automatically generated review topic title."""

    title: str = Field(..., description="A concise, specific title for the review session.")


class LLMQuestionResponse(BaseModel):
    """
    Expected JSON structure for a generated question.
    """
    question: str = Field(..., description="The clarifying question to ask the user.")
