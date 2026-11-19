"""REST endpoints for enquiry submission, CSV upload, and retrieval."""

import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from database import get_db
from models import Enquiry, EnquiryAnalysis
from schemas import EnquiryCreate, EnquiryDetail, EnquiryListItem, EnquiryResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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

    result = process_enquiry(payload, db)
    return result


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

    start_time = time.time()
    content = file.file.read()
    rows, parse_errors = parse_csv(content)

    results = []
    processing_errors = []
    high_count = 0
    med_count = 0
    low_count = 0
    review_count = 0
    dup_count = 0

    for i, row in enumerate(rows):
        try:
            detail = process_enquiry(row, db)
            p = detail.analysis.priority if detail.analysis else "Low"
            if p == "High":
                high_count += 1
            elif p == "Medium":
                med_count += 1
            else:
                low_count += 1

            if detail.enquiry.processing_status in {"NEEDS_REVIEW", "FAILED"} or (
                detail.analysis and detail.analysis.requires_human_review
            ):
                review_count += 1

            if detail.enquiry.is_duplicate:
                dup_count += 1

            results.append(
                {
                    "row": i + 1,
                    "enquiry_id": detail.enquiry.id,
                    "status": detail.enquiry.processing_status,
                    "priority": p,
                    "is_duplicate": detail.enquiry.is_duplicate,
                }
            )
        except Exception as exc:
            logger.error("Pipeline failed for CSV row %d: %s", i + 1, exc)
            processing_errors.append({"row": i + 1, "error": str(exc)})

    duration = round(time.time() - start_time, 2)

    return {
        "total": len(rows) + len(parse_errors),
        "processed": len(results),
        "failed": len(processing_errors) + len(parse_errors),
        "high_priority": high_count,
        "medium_priority": med_count,
        "low_priority": low_count,
        "needs_review": review_count,
        "duplicates_detected": dup_count,
        "duration_seconds": duration,
        "results": results,
        "parse_errors": parse_errors,
        "processing_errors": processing_errors,
    }


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
            is_duplicate=enq.is_duplicate,
            category=enq.analysis.category if enq.analysis else None,
            priority=enq.analysis.priority if enq.analysis else None,
            lead_score=enq.analysis.lead_score if enq.analysis else None,
        )
        items.append(item)

    return items


@router.get(
    "/enquiries/export-csv",
    summary="Export enquiries to CSV file",
)
def api_export_enquiries_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    from app.utils.csv_processor import export_enquiries_to_csv

    query = db.query(Enquiry)
    if status_filter:
        query = query.filter(Enquiry.processing_status == status_filter.upper())
    if category or priority:
        query = query.join(EnquiryAnalysis, Enquiry.id == EnquiryAnalysis.enquiry_id)
        if category:
            query = query.filter(EnquiryAnalysis.category == category)
        if priority:
            query = query.filter(EnquiryAnalysis.priority == priority)

    enquiries = query.order_by(Enquiry.created_at.desc()).all()
    csv_data = export_enquiries_to_csv(enquiries)
    filename = f"enquiries_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
            "qualification_missing_info": a.qualification_missing_info_list,
            "clarification_questions": a.clarification_questions_list,
            "requires_human_review": a.requires_human_review,
            "review_reason": a.review_reason,
            "created_at": a.created_at,
        }

    from schemas import AnalysisResponse, EnquiryResponse, DraftResponse
    draft_obj = None
    if enquiry.draft:
        d = enquiry.draft
        draft_obj = DraftResponse(
            id=d.id,
            enquiry_id=d.enquiry_id,
            subject=d.subject,
            body=d.body,
            approval_status=d.approval_status,
            validation_status=d.validation_status,
            validation_issues=d.validation_issues_list,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )

    return EnquiryDetail(
        enquiry=EnquiryResponse.model_validate(enquiry),
        analysis=AnalysisResponse(**analysis_schema) if analysis_schema else None,
        draft=draft_obj,
    )
