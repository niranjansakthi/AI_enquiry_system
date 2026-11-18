"""
app/routers/drafts.py
─────────────────────
REST endpoints for managing AI-generated email drafts.

PUT   /api/drafts/{id}          – edit subject or body
POST  /api/drafts/{id}/approve  – mark as approved
POST  /api/drafts/{id}/reject   – mark as rejected
POST  /api/drafts/{id}/flag     – mark as needs follow-up
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import ApprovalStatus, ResponseDraft
from schemas import DraftResponse, DraftUpdate, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_draft_or_404(draft_id: int, db: Session) -> ResponseDraft:
    draft = db.query(ResponseDraft).filter(ResponseDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found.",
        )
    return draft


# ─────────────────────────────────────────────────────────────────────────────
# PUT /api/drafts/{id}
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/drafts/{draft_id}",
    response_model=DraftResponse,
    summary="Edit a draft subject or body",
)
def update_draft(draft_id: int, payload: DraftUpdate, db: Session = Depends(get_db)):
    """
    Allows a human reviewer to edit the subject and/or body of a draft
    before approving it. Editing a draft does not change its approval status.
    """
    draft = _get_draft_or_404(draft_id, db)

    if payload.subject is not None:
        draft.subject = payload.subject
    if payload.body is not None:
        draft.body = payload.body

    draft.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(draft)

    logger.info("Draft %d updated by reviewer.", draft_id)
    return DraftResponse.model_validate(draft)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/drafts/{id}/approve
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/drafts/{draft_id}/approve",
    response_model=SuccessResponse,
    summary="Approve a draft",
)
def approve_draft(draft_id: int, db: Session = Depends(get_db)):
    """
    Marks the draft as approved. No email is sent — approval only
    updates the database status for record-keeping.
    """
    draft = _get_draft_or_404(draft_id, db)
    draft.approval_status = ApprovalStatus.APPROVED.value
    draft.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("Draft %d approved.", draft_id)
    return SuccessResponse(message=f"Draft {draft_id} approved successfully.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/drafts/{id}/reject
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/drafts/{draft_id}/reject",
    response_model=SuccessResponse,
    summary="Reject a draft",
)
def reject_draft(draft_id: int, db: Session = Depends(get_db)):
    """
    Marks the draft as rejected. The enquiry remains in the system
    and can be manually responded to or reprocessed.
    """
    draft = _get_draft_or_404(draft_id, db)
    draft.approval_status = ApprovalStatus.REJECTED.value
    draft.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("Draft %d rejected.", draft_id)
    return SuccessResponse(message=f"Draft {draft_id} rejected.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/drafts/{id}/flag
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/drafts/{draft_id}/flag",
    response_model=SuccessResponse,
    summary="Flag a draft for follow-up",
)
def flag_draft(draft_id: int, db: Session = Depends(get_db)):
    """
    Marks the draft as requiring further attention before a decision.
    Useful for escalated or ambiguous enquiries.
    """
    draft = _get_draft_or_404(draft_id, db)
    draft.approval_status = ApprovalStatus.NEEDS_FOLLOWUP.value
    draft.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("Draft %d flagged for follow-up.", draft_id)
    return SuccessResponse(message=f"Draft {draft_id} flagged for follow-up.")
