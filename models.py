"""Data models and schemas for lead objects."""

from __future__ import annotations

from typing import List, Literal
from pydantic import BaseModel, Field


class LeadInput(BaseModel):
    full_name: str
    email: str
    company_name: str = ""
    job_title: str = ""
    phone: str = ""
    company_size: str = ""
    budget_range: str = ""
    message: str = ""


class NormalizedLead(LeadInput):
    full_name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    company_size: str = Field(min_length=1)
    budget_range: str = Field(min_length=1)
    message: str = Field(min_length=1)
    timestamp: str


class AIAnalysis(BaseModel):
    lead_score: int = Field(..., ge=0, le=100)
    priority_tier: Literal["Hot", "Warm", "Cold", "Manual Review"]
    intent_summary: str
    suggested_opener: str
    red_flags: List[str]


class EnrichedLead(NormalizedLead, AIAnalysis):
    pass


class WebhookResponse(BaseModel):
    request_id: str           # UUID for tracking
    status: str               # "qualified" | "rejected" | "low_context" | "timeout"
    priority_tier: str        # Hot | Warm | Cold | Manual Review | Invalid
    lead_score: int           # 0-100
    next_step: str            # Personalized message for the caller
    response_time_ms: int     # How long the full pipeline took
    version: str              # APP_VERSION

