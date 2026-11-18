"""
schemas.py
──────────
All Pydantic models used for request validation, response serialisation,
and AI output validation.

Sections:
  1. Enquiry input / output schemas
  2. AI extraction schema (Module B output)
  3. Lead score schema (Module C output)
  4. Response draft schemas (Module D)
  5. Pipeline result schema (Module E)
  6. Dashboard / stats schemas
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# 1. Enquiry input / output
# ─────────────────────────────────────────────────────────────────────────────

VALID_SOURCES = {"web_form", "api", "csv_upload"}


class EnquiryCreate(BaseModel):
    """
    Schema for submitting a new enquiry.

    All customer-identifying fields are optional because enquiries often
    arrive without complete contact information. Only the message is required.
    """
    customer_name: Optional[str] = Field(None, max_length=200)
    company_name: Optional[str] = Field(None, max_length=200)
    email: Optional[EmailStr] = None
    message: str = Field(..., min_length=5, max_length=5000)
    source: str = Field(default="api")

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in VALID_SOURCES:
            raise ValueError(f"source must be one of: {', '.join(sorted(VALID_SOURCES))}")
        return v

    @field_validator("customer_name", "company_name", mode="before")
    @classmethod
    def strip_blank_strings(cls, v):
        """Treat whitespace-only strings as None."""
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Message is too short to process meaningfully.")
        return v


class EnquiryResponse(BaseModel):
    """Full enquiry row returned from the database."""
    id: int
    customer_name: Optional[str]
    company_name: Optional[str]
    email: Optional[str]
    message: str
    source: str
    processing_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EnquiryListItem(BaseModel):
    """Compact row used in the enquiry list view."""
    id: int
    customer_name: Optional[str]
    company_name: Optional[str]
    email: Optional[str]
    source: str
    processing_status: str
    created_at: datetime
    # Populated from the joined analysis row when available
    category: Optional[str] = None
    priority: Optional[str] = None
    lead_score: Optional[int] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# 2. AI extraction schema — Module B output
# ─────────────────────────────────────────────────────────────────────────────

VALID_CATEGORIES = {
    "Business Consulting",
    "AI Automation",
    "Website Development",
    "Application Development",
    "Branding and Marketing",
    "General Enquiry",
    "Job and Internship Application",
    "Partnership",
    "Complaint",
    "Other",
}


class ExtractedInfo(BaseModel):
    """
    Structured output from the AI understanding service.

    Every field that the AI could not determine must be null.
    The confidence score must be between 0 and 1.
    """
    category: str
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    requirement: Optional[str] = None
    budget: Optional[str] = None
    expected_timeline: Optional[str] = None
    intent: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_human_review: bool = False
    review_reason: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            # Accept closest match rather than hard-failing; fall back to Other
            return "Other"
        return v

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 4)

    @field_validator("customer_name", "company_name", "requirement",
                     "budget", "expected_timeline", "intent",
                     "review_reason", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


# ─────────────────────────────────────────────────────────────────────────────
# 3. Lead score schema — Module C output
# ─────────────────────────────────────────────────────────────────────────────

VALID_PRIORITIES = {"High", "Medium", "Low"}


class LeadScore(BaseModel):
    """
    Output from the Python lead scoring function.

    score    : 0–100, calculated from five weighted dimensions
    priority : High (70–100) | Medium (40–69) | Low (0–39)
    reasons  : human-readable explanation of each scoring decision
    """
    score: int = Field(..., ge=0, le=100)
    priority: str
    reasons: list[str]

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# 4. Response draft schemas — Module D
# ─────────────────────────────────────────────────────────────────────────────

class DraftContent(BaseModel):
    """Raw output from the AI response generation service."""
    subject: str = Field(..., min_length=3, max_length=500)
    body: str = Field(..., min_length=10)


class DraftResponse(BaseModel):
    """Full draft row returned from the database."""
    id: int
    enquiry_id: int
    subject: Optional[str]
    body: Optional[str]
    approval_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DraftUpdate(BaseModel):
    """Request body for editing a draft."""
    subject: Optional[str] = Field(None, min_length=3, max_length=500)
    body: Optional[str] = Field(None, min_length=10)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DraftUpdate":
        if self.subject is None and self.body is None:
            raise ValueError("Provide at least one of: subject, body")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 5. Pipeline result — Module E output
# ─────────────────────────────────────────────────────────────────────────────

class AnalysisResponse(BaseModel):
    """Serialised EnquiryAnalysis row."""
    id: int
    enquiry_id: int
    category: Optional[str]
    requirement: Optional[str]
    budget: Optional[str]
    expected_timeline: Optional[str]
    intent: Optional[str]
    confidence: Optional[float]
    lead_score: Optional[int]
    priority: Optional[str]
    scoring_reasons: Optional[list[str]] = None
    requires_human_review: bool
    review_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class EnquiryDetail(BaseModel):
    """
    Full enquiry record including analysis and draft.
    Returned by GET /api/enquiries/{id} and the pipeline result.
    """
    enquiry: EnquiryResponse
    analysis: Optional[AnalysisResponse] = None
    draft: Optional[DraftResponse] = None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Dashboard / stats schemas
# ─────────────────────────────────────────────────────────────────────────────

class PriorityStats(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0
    unscored: int = 0


class StatusStats(BaseModel):
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    needs_review: int = 0


class DashboardStats(BaseModel):
    total_enquiries: int
    priority: PriorityStats
    status: StatusStats
    pending_human_reviews: int
    approved_drafts: int = 0
    category_breakdown: dict[str, int]


# ─────────────────────────────────────────────────────────────────────────────
# 7. Generic API response wrappers
# ─────────────────────────────────────────────────────────────────────────────

class SuccessResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None

