"""Database models for enquiries, analysis, and response drafts."""

import enum
import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class ProcessingStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_FOLLOWUP = "NEEDS_FOLLOWUP"


class EnquirySource(str, enum.Enum):
    WEB_FORM = "web_form"
    API = "api"
    CSV_UPLOAD = "csv_upload"


class Enquiry(Base):
    __tablename__ = "enquiries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default=EnquirySource.API.value
    )
    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProcessingStatus.PENDING.value
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Duplicate detection
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    analysis: Mapped["EnquiryAnalysis | None"] = relationship(
        "EnquiryAnalysis", back_populates="enquiry", uselist=False, cascade="all, delete-orphan"
    )
    draft: Mapped["ResponseDraft | None"] = relationship(
        "ResponseDraft", back_populates="enquiry", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Enquiry id={self.id} status={self.processing_status}>"


class EnquiryAnalysis(Base):
    __tablename__ = "enquiry_analysis"
    __table_args__ = (
        UniqueConstraint("enquiry_id", name="uq_analysis_enquiry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enquiry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False
    )

    # Extracted fields
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expected_timeline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Scoring
    lead_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scoring_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Review flags
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Qualification & clarification questions
    qualification_missing_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_questions: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    enquiry: Mapped["Enquiry"] = relationship("Enquiry", back_populates="analysis")

    @property
    def scoring_reasons_list(self) -> list[str]:
        if not self.scoring_reasons:
            return []
        try:
            return json.loads(self.scoring_reasons)
        except (json.JSONDecodeError, TypeError):
            return []

    @scoring_reasons_list.setter
    def scoring_reasons_list(self, value: list[str]) -> None:
        self.scoring_reasons = json.dumps(value)

    @property
    def qualification_missing_info_list(self) -> list[str]:
        if not self.qualification_missing_info:
            return []
        try:
            return json.loads(self.qualification_missing_info)
        except (json.JSONDecodeError, TypeError):
            return []

    @qualification_missing_info_list.setter
    def qualification_missing_info_list(self, value: list[str]) -> None:
        self.qualification_missing_info = json.dumps(value)

    @property
    def clarification_questions_list(self) -> list[str]:
        if not self.clarification_questions:
            return []
        try:
            return json.loads(self.clarification_questions)
        except (json.JSONDecodeError, TypeError):
            return []

    @clarification_questions_list.setter
    def clarification_questions_list(self, value: list[str]) -> None:
        self.clarification_questions = json.dumps(value)

    def __repr__(self) -> str:
        return f"<EnquiryAnalysis enquiry_id={self.enquiry_id} score={self.lead_score}>"


class ResponseDraft(Base):
    __tablename__ = "response_drafts"
    __table_args__ = (
        UniqueConstraint("enquiry_id", name="uq_draft_enquiry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enquiry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False
    )

    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalStatus.PENDING.value
    )

    # Validation tracking
    validation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PASSED"
    )
    validation_issues: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    enquiry: Mapped["Enquiry"] = relationship("Enquiry", back_populates="draft")

    @property
    def validation_issues_list(self) -> list[str]:
        if not self.validation_issues:
            return []
        try:
            return json.loads(self.validation_issues)
        except (json.JSONDecodeError, TypeError):
            return []

    @validation_issues_list.setter
    def validation_issues_list(self, value: list[str]) -> None:
        self.validation_issues = json.dumps(value)

    def __repr__(self) -> str:
        return f"<ResponseDraft enquiry_id={self.enquiry_id} status={self.approval_status}>"

