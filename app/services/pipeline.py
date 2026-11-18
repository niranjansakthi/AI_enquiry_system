"""
app/services/pipeline.py
─────────────────────────
Module E: Central automation pipeline.

Single public function: process_enquiry(payload, db) -> EnquiryDetail

Steps:
  1. Validate input (Pydantic handles this before the function is called)
  2. Save the original enquiry with status PENDING
  3. Set status to PROCESSING
  4. Call AI understanding service (Module B)
  5. Validate extracted information
  6. Calculate lead score using Python (Module C)
  7. Determine priority and human review flags
  8. Generate email draft (Module D)
  9. Save EnquiryAnalysis and ResponseDraft to the database
  10. Set final status (COMPLETED or NEEDS_REVIEW)
  11. Return full EnquiryDetail

Failure handling:
  - If AI extraction fails: enquiry is saved as FAILED, no analysis created
  - If draft generation fails: analysis is saved, draft skipped, status = NEEDS_REVIEW
  - The original enquiry is NEVER lost regardless of downstream failures
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import ESCALATION_CATEGORIES
from models import Enquiry, EnquiryAnalysis, ProcessingStatus, ResponseDraft
from schemas import (
    AnalysisResponse,
    DraftResponse,
    EnquiryCreate,
    EnquiryDetail,
    EnquiryResponse,
)

logger = logging.getLogger(__name__)


def process_enquiry(payload: EnquiryCreate, db: Session) -> EnquiryDetail:
    """
    Run an enquiry through the full automation pipeline.

    Args:
        payload : validated EnquiryCreate from the API layer
        db      : active SQLAlchemy session

    Returns:
        EnquiryDetail with enquiry, analysis, and draft populated
    """
    from app.services.ai_understanding import AIExtractionError, extract_enquiry_info
    from app.services.ai_response import AIResponseError, generate_email_draft
    from app.services.lead_scoring import calculate_lead_score

    # ── Step 2: Save original enquiry ─────────────────────────────────────
    enquiry = Enquiry(
        customer_name=payload.customer_name,
        company_name=payload.company_name,
        email=payload.email,
        message=payload.message,
        source=payload.source,
        processing_status=ProcessingStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)
    logger.info("Enquiry %d saved (status=PENDING).", enquiry.id)

    # ── Step 3: Mark as processing ────────────────────────────────────────
    enquiry.processing_status = ProcessingStatus.PROCESSING.value
    db.commit()

    # ── Step 4: AI extraction ─────────────────────────────────────────────
    try:
        extracted = extract_enquiry_info(
            message=enquiry.message,
            existing_name=enquiry.customer_name,
            existing_email=enquiry.email,
        )
    except AIExtractionError as exc:
        logger.error("AI extraction failed for enquiry %d: %s", enquiry.id, exc)
        enquiry.processing_status = ProcessingStatus.FAILED.value
        db.commit()
        return _build_detail(enquiry, analysis_row=None, draft_row=None, db=db)

    # ── Step 6: Lead scoring (pure Python) ───────────────────────────────
    lead_score = calculate_lead_score(extracted)

    # ── Step 7: Human review flags ────────────────────────────────────────
    # Categories that always require escalation, regardless of score
    if extracted.category in ESCALATION_CATEGORIES:
        extracted.requires_human_review = True
        if not extracted.review_reason:
            extracted.review_reason = (
                f"Category '{extracted.category}' requires human evaluation."
            )

    final_status = (
        ProcessingStatus.NEEDS_REVIEW.value
        if extracted.requires_human_review
        else ProcessingStatus.COMPLETED.value
    )

    # ── Step 9a: Save EnquiryAnalysis ─────────────────────────────────────
    analysis_row = EnquiryAnalysis(
        enquiry_id=enquiry.id,
        category=extracted.category,
        requirement=extracted.requirement,
        budget=extracted.budget,
        expected_timeline=extracted.expected_timeline,
        intent=extracted.intent,
        confidence=extracted.confidence,
        lead_score=lead_score.score,
        priority=lead_score.priority,
        scoring_reasons=json.dumps(lead_score.reasons),
        requires_human_review=extracted.requires_human_review,
        review_reason=extracted.review_reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis_row)
    db.commit()
    db.refresh(analysis_row)
    logger.info(
        "Analysis saved for enquiry %d: score=%d priority=%s requires_review=%s",
        enquiry.id, lead_score.score, lead_score.priority, extracted.requires_human_review,
    )

    # ── Step 8: Generate email draft ──────────────────────────────────────
    draft_row = None
    try:
        draft_content = generate_email_draft(
            enquiry_message=enquiry.message,
            extracted=extracted,
            lead_score=lead_score,
        )
        draft_row = ResponseDraft(
            enquiry_id=enquiry.id,
            subject=draft_content.subject,
            body=draft_content.body,
            approval_status="PENDING",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(draft_row)
        db.commit()
        db.refresh(draft_row)
        logger.info("Draft saved for enquiry %d.", enquiry.id)

    except AIResponseError as exc:
        logger.error("Draft generation failed for enquiry %d: %s", enquiry.id, exc)
        # Draft failure is not fatal — save analysis without a draft
        final_status = ProcessingStatus.NEEDS_REVIEW.value

    # ── Step 10: Final status ─────────────────────────────────────────────
    enquiry.processing_status = final_status
    db.commit()
    logger.info("Enquiry %d pipeline complete (status=%s).", enquiry.id, final_status)

    return _build_detail(enquiry, analysis_row, draft_row, db)


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _build_detail(
    enquiry: Enquiry,
    analysis_row: EnquiryAnalysis | None,
    draft_row: ResponseDraft | None,
    db: Session,
) -> EnquiryDetail:
    """Construct the EnquiryDetail response schema from ORM objects."""
    db.refresh(enquiry)

    analysis_schema = None
    if analysis_row:
        db.refresh(analysis_row)
        analysis_schema = AnalysisResponse(
            id=analysis_row.id,
            enquiry_id=analysis_row.enquiry_id,
            category=analysis_row.category,
            requirement=analysis_row.requirement,
            budget=analysis_row.budget,
            expected_timeline=analysis_row.expected_timeline,
            intent=analysis_row.intent,
            confidence=analysis_row.confidence,
            lead_score=analysis_row.lead_score,
            priority=analysis_row.priority,
            scoring_reasons=analysis_row.scoring_reasons_list,
            requires_human_review=analysis_row.requires_human_review,
            review_reason=analysis_row.review_reason,
            created_at=analysis_row.created_at,
        )

    draft_schema = None
    if draft_row:
        db.refresh(draft_row)
        draft_schema = DraftResponse.model_validate(draft_row)

    return EnquiryDetail(
        enquiry=EnquiryResponse.model_validate(enquiry),
        analysis=analysis_schema,
        draft=draft_schema,
    )

