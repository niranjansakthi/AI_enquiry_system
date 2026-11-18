"""
app/routers/enquiries.py
────────────────────────
REST endpoints for enquiry submission and retrieval.

POST  /api/enquiries            – submit and process a single enquiry
POST  /api/enquiries/upload-csv – upload and process a CSV batch
GET   /api/enquiries            – list enquiries with optional filters + pagination
GET   /api/enquiries/{id}       – full enquiry details with analysis and draft
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from database import get_db
from models import Enquiry, EnquiryAnalysis
from schemas import EnquiryCreate, EnquiryDetail, EnquiryListItem, EnquiryResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/enquiries
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/enquiries",
    response_model=EnquiryDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Submit and process a single enquiry",
)
def submit_enquiry(payload: EnquiryCreate, db: Session = Depends(get_db)):
    """
    Accepts a validated enquiry, runs it through the full automation
    pipeline (AI extraction → scoring → draft generation) and returns
    the completed result.

    If the AI pipeline fails the original enquiry is still saved and
    returned with status FAILED or NEEDS_REVIEW.
    """
    from app.services.pipeline import process_enquiry

    # Duplicate guard: same email + identical message submitted within the
    # same session. Not a hard block — just a warning in the log.
    if payload.email:
        existing = (
            db.query(Enquiry)
            .filter(Enquiry.email == payload.email, Enquiry.message == payload.message)
            .first()
        )
        if existing:
            logger.warning(
                "Possible duplicate enquiry from %s (matches enquiry id=%s)",
                payload.email,
                existing.id,
            )

    result = process_enquiry(payload, db)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/enquiries/upload-csv
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/enquiries/upload-csv",
    summary="Upload a CSV file and process all enquiries in it",
)
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Accepts a CSV file. Each row is processed through the pipeline.
    Rows that fail validation are skipped and reported in the response.
    Rows that pass validation but fail AI processing are saved with
    status FAILED so they can be retried manually.
    """
    from app.services.pipeline import process_enquiry
    from app.utils.csv_processor import parse_csv

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted.",
        )

    content = file.file.read()
    rows, parse_errors = parse_csv(content)

    results = []
    processing_errors = []

    for i, row in enumerate(rows):
        try:
            detail = process_enquiry(row, db)
            results.append(
                {
                    "row": i + 1,
                    "enquiry_id": detail.enquiry.id,
                    "status": detail.enquiry.processing_status,
                }
            )
        except Exception as exc:
            logger.error("Pipeline failed for CSV row %d: %s", i + 1, exc)
            processing_errors.append({"row": i + 1, "error": str(exc)})

    return {
        "processed": len(results),
        "failed": len(processing_errors) + len(parse_errors),
        "results": results,
        "parse_errors": parse_errors,
        "processing_errors": processing_errors,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/enquiries
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/enquiries",
    response_model=list[EnquiryListItem],
    summary="List enquiries with optional filters",
)
def list_enquiries(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search in message, name and company"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Returns a paginated list of enquiries.

    Optional filters:
    - status   : PENDING | PROCESSING | COMPLETED | FAILED | NEEDS_REVIEW
    - category : any valid enquiry category
    - priority : High | Medium | Low
    - search   : substring match on message, customer_name, company_name
    """
    query = db.query(Enquiry)

    if status_filter:
        query = query.filter(Enquiry.processing_status == status_filter.upper())

    if search:
        term = f"%{search}%"
        query = query.filter(
            Enquiry.message.ilike(term)
            | Enquiry.customer_name.ilike(term)
            | Enquiry.company_name.ilike(term)
        )

    # Join analysis only when category or priority filter is applied
    if category or priority:
        query = query.join(EnquiryAnalysis, Enquiry.id == EnquiryAnalysis.enquiry_id)
        if category:
            query = query.filter(EnquiryAnalysis.category == category)
        if priority:
            query = query.filter(EnquiryAnalysis.priority == priority)

    total = query.count()
    enquiries = (
        query.order_by(Enquiry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for enq in enquiries:
        item = EnquiryListItem(
            id=enq.id,
            customer_name=enq.customer_name,
            company_name=enq.company_name,
            email=enq.email,
            source=enq.source,
            processing_status=enq.processing_status,
            created_at=enq.created_at,
            category=enq.analysis.category if enq.analysis else None,
            priority=enq.analysis.priority if enq.analysis else None,
            lead_score=enq.analysis.lead_score if enq.analysis else None,
        )
        items.append(item)

    return items


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/enquiries/{id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/enquiries/{enquiry_id}",
    response_model=EnquiryDetail,
    summary="Get one enquiry with its analysis and email draft",
)
def get_enquiry(enquiry_id: int, db: Session = Depends(get_db)):
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Enquiry {enquiry_id} not found.",
        )

    analysis_schema = None
    if enquiry.analysis:
        a = enquiry.analysis
        analysis_schema = {
            "id": a.id,
            "enquiry_id": a.enquiry_id,
            "category": a.category,
            "requirement": a.requirement,
            "budget": a.budget,
            "expected_timeline": a.expected_timeline,
            "intent": a.intent,
            "confidence": a.confidence,
            "lead_score": a.lead_score,
            "priority": a.priority,
            "scoring_reasons": a.scoring_reasons_list,
            "requires_human_review": a.requires_human_review,
            "review_reason": a.review_reason,
            "created_at": a.created_at,
        }

    from schemas import AnalysisResponse, EnquiryResponse, DraftResponse
    return EnquiryDetail(
        enquiry=EnquiryResponse.model_validate(enquiry),
        analysis=AnalysisResponse(**analysis_schema) if analysis_schema else None,
        draft=DraftResponse.model_validate(enquiry.draft) if enquiry.draft else None,
    )
