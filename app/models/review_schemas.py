"""
Pydantic models for validating the structured JSON output from LLMs
during the multi-round review process.
"""
from typing import List
from pydantic import BaseModel, Field

class Disagreement(BaseModel):
    """A model for a disagreement point in the rebuttal round."""
    point: str = Field(..., description="The argument being challenged or refined.")
    reasoning: str = Field(..., description="The logical flaw or reason for the challenge.")

class Addition(BaseModel):
    """A model for a new point raised in the rebuttal round."""
    point: str = Field(..., description="A new consideration missed in the previous round.")
    reasoning: str = Field(..., description="Why this new point is important.")

class LLMReviewInitialAnalysis(BaseModel):
    """
    Expected JSON structure for Round 1 (Initial Analysis).
    """
    round: int
    key_takeaway: str = Field(..., description="A brief summary of the main finding.")
    arguments: List[str] = Field(..., description="A list of core arguments with reasoning.")
    risks: List[str] = Field(..., description="A list of anticipated or potential risks.")
    opportunities: List[str] = Field(..., description="A list of discovered or potential opportunities.")

class LLMReviewRebuttal(BaseModel):
    """
    Expected JSON structure for Round 2 (Rebuttal).
    """
    round: int
    no_new_arguments: bool = Field(
        default=False,
        description="Set to true if the panelist has no meaningful rebuttal to add.",
    )
    agreements: List[str] = Field(..., description="A list of round 1 arguments that are agreed with.")
    disagreements: List[Disagreement] = Field(..., description="A list of points of disagreement with reasoning.")
    additions: List[Addition] = Field(..., description="A list of new points or additions with reasoning.")

class LLMReviewSynthesis(BaseModel):
    """
    Expected JSON structure for Round 3 (Synthesis).
    """
    round: int
    no_new_arguments: bool = Field(
        default=False,
        description="Set to true if the panelist has nothing new to contribute for the alignment round.",
    )
    executive_summary: str = Field(..., description="A high-level summary of the final synthesized position.")
    conclusion: str = Field(..., description="The detailed, comprehensive conclusion supporting the summary.")
    recommendations: List[str] = Field(..., description="A list of specific, actionable recommendations.")

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
