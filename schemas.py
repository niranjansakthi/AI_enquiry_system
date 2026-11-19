"""Pydantic schemas for request validation and response serialization."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Enquiry schemas
VALID_SOURCES = {"web_form", "api", "csv_upload"}


class EnquiryCreate(BaseModel):
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
    id: int
    customer_name: Optional[str]
    company_name: Optional[str]
    email: Optional[str]
    message: str
    source: str
    processing_status: str
    created_at: datetime
    is_duplicate: bool = False
    duplicate_of_id: Optional[int] = None
    duplicate_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class EnquiryListItem(BaseModel):
    id: int
    customer_name: Optional[str]
    company_name: Optional[str]
    email: Optional[str]
    source: str
    processing_status: str
    created_at: datetime
    is_duplicate: bool = False
    category: Optional[str] = None
    priority: Optional[str] = None
    lead_score: Optional[int] = None

    model_config = {"from_attributes": True}


# Extraction schemas
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


# Lead scoring schemas
VALID_PRIORITIES = {"High", "Medium", "Low"}


class LeadScore(BaseModel):
    score: int = Field(..., ge=0, le=100)
    priority: str
    reasons: list[str]

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
        return v


# Response draft schemas
class DraftContent(BaseModel):
    subject: str = Field(..., min_length=3, max_length=500)
    body: str = Field(..., min_length=10)


class DraftResponse(BaseModel):
    id: int
    enquiry_id: int
    subject: Optional[str]
    body: Optional[str]
    approval_status: str
    validation_status: str = "PASSED"
    validation_issues: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("validation_issues", mode="before")
    @classmethod
    def parse_validation_issues(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return [v] if v else []
        return v


class DraftUpdate(BaseModel):
    subject: Optional[str] = Field(None, min_length=3, max_length=500)
    body: Optional[str] = Field(None, min_length=10)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DraftUpdate":
        if self.subject is None and self.body is None:
            raise ValueError("Provide at least one of: subject, body")
        return self


# Analysis & pipeline result schemas
class AnalysisResponse(BaseModel):
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
    qualification_missing_info: Optional[list[str]] = None
    clarification_questions: Optional[list[str]] = None
    requires_human_review: bool
    review_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("scoring_reasons", "qualification_missing_info", "clarification_questions", mode="before")
    @classmethod
    def parse_analysis_json_lists(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return [v] if v else []
        return v


class EnquiryDetail(BaseModel):
    enquiry: EnquiryResponse
    analysis: Optional[AnalysisResponse] = None
    draft: Optional[DraftResponse] = None


# Dashboard metrics schemas
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


# Utility & feature schemas
class SuccessResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None


class DuplicateCheckResult(BaseModel):
    is_duplicate: bool = False
    original_enquiry_id: Optional[int] = None
    original_created_at: Optional[datetime] = None
    similarity_score: float = 0.0
    message: Optional[str] = None


class ValidationIssue(BaseModel):
    code: str
    severity: str
    description: str


class SafetyValidationResult(BaseModel):
    is_safe: bool = True
    status: str = "PASSED"
    issues: list[ValidationIssue] = Field(default_factory=list)
    requires_human_review: bool = False
    explanation: Optional[str] = None


class QualificationResult(BaseModel):
    available_info: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    follow_up_draft: Optional[str] = None


class BatchProcessingReport(BaseModel):
    total_enquiries: int
    processed: int
    failed: int
    high_priority: int
    medium_priority: int
    low_priority: int
    needs_review: int
    duplicates_detected: int
    duration_seconds: float


