"""Pydantic models for validating the structured JSON output from LLMs.

The new conversation-oriented format keeps the multi-round structure but expects
each panelist turn to look like a real chat bubble with explicit cross
references.  Downstream code still relies on structured fields to build light
weight digests for subsequent prompts, so the schema keeps a concise
``key_takeaway`` in addition to the natural language ``message``.
"""

from typing import List, Literal

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

class LLMFinalReport(BaseModel):
    """
    Expected JSON structure for the final consolidated report.
    """
    executive_summary: str = Field(..., description="The final summary, including key insights from the entire discussion.")
    strongest_consensus: List[str] = Field(..., description="Key points that panelists commonly agreed on.")
    remaining_disagreements: List[str] = Field(..., description="Significant disagreements that remained, if any.")
    recommendations: List[str] = Field(..., description="A list of consolidated final recommendations.")

class LLMQuestionResponse(BaseModel):
    """
    Expected JSON structure for a generated question.
    """
    question: str = Field(..., description="The clarifying question to ask the user.")
