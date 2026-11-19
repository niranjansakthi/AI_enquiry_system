"""
app/routers/dashboard.py
────────────────────────
Endpoints for dashboard statistics, health check, and HTML views.

Endpoints:
  GET  /api/health           – Application health check
  GET  /api/dashboard/stats  – Aggregated counts, priority, and category stats
  GET  /                     – HTML dashboard (stats + quick view)
  GET  /enquiries            – HTML enquiry list view with filters & search
  GET  /enquiries/new        – HTML form for manual enquiry submission
  GET  /enquiries/{id}       – HTML enquiry detail view (analysis + editable draft)
  GET  /review               – HTML review queue (pending reviews & drafts)
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import ApprovalStatus, Enquiry, EnquiryAnalysis, ProcessingStatus, ResponseDraft
from schemas import (
    DashboardStats,
    EnquiryCreate,
    PriorityStats,
    StatusStats,
)

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ─────────────────────────────────────────────────────────────────────────────
# 1. API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/health", summary="Application health check")
def health_check():
    return {
        "status": "ok",
        "service": "Curd Rice Business Studio - Enquiry Automation System",
    }


@router.get(
    "/api/dashboard/stats",
    response_model=DashboardStats,
    summary="Dashboard metrics & statistics",
)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Computes real-time aggregated metrics across all enquiries.
    """
    total = db.query(Enquiry).count()

    # Priorities
    priority_counts = (
        db.query(EnquiryAnalysis.priority, func.count(EnquiryAnalysis.id))
        .group_by(EnquiryAnalysis.priority)
        .all()
    )
    p_map = {p: count for p, count in priority_counts if p}
    priority_stats = PriorityStats(
        high=p_map.get("High", 0),
        medium=p_map.get("Medium", 0),
        low=p_map.get("Low", 0),
        unscored=total - sum(p_map.values()),
    )

    # Statuses
    status_counts = (
        db.query(Enquiry.processing_status, func.count(Enquiry.id))
        .group_by(Enquiry.processing_status)
        .all()
    )
    s_map = {s: count for s, count in status_counts if s}
    status_stats = StatusStats(
        pending=s_map.get(ProcessingStatus.PENDING.value, 0),
        processing=s_map.get(ProcessingStatus.PROCESSING.value, 0),
        completed=s_map.get(ProcessingStatus.COMPLETED.value, 0),
        failed=s_map.get(ProcessingStatus.FAILED.value, 0),
        needs_review=s_map.get(ProcessingStatus.NEEDS_REVIEW.value, 0),
    )

    # Pending human reviews: either marked requires_human_review or draft is PENDING
    pending_reviews = (
        db.query(Enquiry)
        .outerjoin(EnquiryAnalysis, Enquiry.id == EnquiryAnalysis.enquiry_id)
        .outerjoin(ResponseDraft, Enquiry.id == ResponseDraft.enquiry_id)
        .filter(
            (Enquiry.processing_status == ProcessingStatus.NEEDS_REVIEW.value)
            | (EnquiryAnalysis.requires_human_review == True)
            | (ResponseDraft.approval_status == ApprovalStatus.PENDING.value)
        )
        .distinct()
        .count()
    )

    # Category breakdown
    category_counts = (
        db.query(EnquiryAnalysis.category, func.count(EnquiryAnalysis.id))
        .filter(EnquiryAnalysis.category != None)
        .group_by(EnquiryAnalysis.category)
        .all()
    )
    cat_map = {cat: count for cat, count in category_counts}

    # Approved drafts count
    approved_drafts_count = (
        db.query(ResponseDraft)
        .filter(ResponseDraft.approval_status == ApprovalStatus.APPROVED.value)
        .count()
    )

    return DashboardStats(
        total_enquiries=total,
        priority=priority_stats,
        status=status_stats,
        pending_human_reviews=pending_reviews,
        approved_drafts=approved_drafts_count,
        category_breakdown=cat_map,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. HTML View Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, summary="Dashboard UI")
def view_dashboard(request: Request, db: Session = Depends(get_db)):
    stats = get_dashboard_stats(db)
    recent_enquiries = (
        db.query(Enquiry)
        .order_by(Enquiry.created_at.desc())
        .limit(8)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "stats": stats,
            "recent_enquiries": recent_enquiries,
        },
    )


@router.get("/enquiries", response_class=HTMLResponse, summary="Enquiry list UI")
def view_enquiry_list(
    request: Request,
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Enquiry)

    if status:
        query = query.filter(Enquiry.processing_status == status.upper())

    if search:
        term = f"%{search}%"
        query = query.filter(
            Enquiry.message.ilike(term)
            | Enquiry.customer_name.ilike(term)
            | Enquiry.company_name.ilike(term)
        )

    if category or priority:
        query = query.join(EnquiryAnalysis, Enquiry.id == EnquiryAnalysis.enquiry_id)
        if category:
            query = query.filter(EnquiryAnalysis.category == category)
        if priority:
            query = query.filter(EnquiryAnalysis.priority == priority)

    enquiries = query.order_by(Enquiry.created_at.desc()).all()

    from config import ENQUIRY_CATEGORIES
    return templates.TemplateResponse(
        request=request,
        name="enquiry_list.html",
        context={
            "enquiries": enquiries,
            "categories": ENQUIRY_CATEGORIES,
            "selected_status": status or "",
            "selected_category": category or "",
            "selected_priority": priority or "",
            "search_query": search or "",
        },
    )


@router.get("/upload-csv", response_class=HTMLResponse, summary="CSV Upload Page")
def view_upload_csv(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="upload_csv.html",
        context={"result": None, "error": None},
    )


@router.post("/upload-csv", response_class=HTMLResponse, summary="Handle CSV Upload from Form")
def handle_upload_csv_form(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    from app.services.pipeline import process_enquiry
    from app.utils.csv_processor import parse_csv

    if not file.filename or not file.filename.lower().endswith(".csv"):
        return templates.TemplateResponse(
            request=request,
            name="upload_csv.html",
            context={"result": None, "error": "Only CSV files are allowed."},
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
    duplicates_count = 0

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
                duplicates_count += 1

            results.append({
                "row": i + 1,
                "enquiry_id": detail.enquiry.id,
                "status": detail.enquiry.processing_status,
                "customer": detail.enquiry.customer_name or "Anonymous",
                "category": detail.analysis.category if detail.analysis else "N/A",
                "score": detail.analysis.lead_score if detail.analysis else 0,
                "priority": p,
                "is_duplicate": detail.enquiry.is_duplicate,
            })
        except Exception as exc:
            processing_errors.append({"row": i + 1, "error": str(exc)})

    duration = round(time.time() - start_time, 2)

    return templates.TemplateResponse(
        request=request,
        name="upload_csv.html",
        context={
            "result": {
                "total": len(rows) + len(parse_errors),
                "processed": len(results),
                "failed": len(processing_errors) + len(parse_errors),
                "high_priority": high_count,
                "medium_priority": med_count,
                "low_priority": low_count,
                "needs_review": review_count,
                "duplicates_detected": duplicates_count,
                "duration_seconds": duration,
                "processed_items": results,
                "items": results,
                "parse_errors": parse_errors,
                "processing_errors": processing_errors,
            },
            "error": None,
        },
    )


@router.get("/enquiries/export-csv", summary="Export enquiries to CSV")
def export_enquiries_csv(
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from app.utils.csv_processor import export_enquiries_to_csv

    query = db.query(Enquiry)

    if status:
        query = query.filter(Enquiry.processing_status == status.upper())

    if category or priority:
        query = query.join(EnquiryAnalysis, Enquiry.id == EnquiryAnalysis.enquiry_id)
        if category:
            query = query.filter(EnquiryAnalysis.category == category)
        if priority:
            query = query.filter(EnquiryAnalysis.priority == priority)

    enquiries = query.order_by(Enquiry.created_at.desc()).all()
    csv_data = export_enquiries_to_csv(enquiries)

    filename = f"curd_rice_enquiries_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@router.get("/analytics", response_class=HTMLResponse, summary="Analytics UI")
def view_analytics(request: Request, db: Session = Depends(get_db)):
    stats = get_dashboard_stats(db)
    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={"stats": stats},
    )


@router.get("/about", response_class=HTMLResponse, summary="About UI")
def view_about(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={},
    )


@router.get("/enquiries/new", response_class=HTMLResponse, summary="Manual enquiry form")
def view_new_enquiry_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="new_enquiry.html",
        context={"error": None},
    )


@router.post("/enquiries/new", response_class=HTMLResponse, summary="Process submitted manual enquiry")
def handle_new_enquiry_form(
    request: Request,
    customer_name: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    message: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.services.pipeline import process_enquiry
    from pydantic import ValidationError

    try:
        payload = EnquiryCreate(
            customer_name=customer_name,
            company_name=company_name,
            email=email if email and email.strip() else None,
            message=message,
            source="web_form",
        )
    except ValidationError as exc:
        err_msg = exc.errors()[0]["msg"]
        return templates.TemplateResponse(
            request=request,
            name="new_enquiry.html",
            context={
                "error": err_msg,
                "customer_name": customer_name,
                "company_name": company_name,
                "email": email,
                "message": message,
            },
        )

    result = process_enquiry(payload, db)
    return RedirectResponse(url=f"/enquiries/{result.enquiry.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/enquiries/{enquiry_id}", response_class=HTMLResponse, summary="Enquiry detail and draft editor")
def view_enquiry_detail(enquiry_id: int, request: Request, db: Session = Depends(get_db)):
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    gmail_url = None
    mailto_url = None
    if enquiry.draft and enquiry.draft.body:
        from app.utils.email_compose import generate_gmail_compose_url, generate_mailto_url
        subject = enquiry.draft.subject or f"Regarding your inquiry with Curd Rice Business Studio"
        gmail_url = generate_gmail_compose_url(
            recipient=enquiry.email,
            subject=subject,
            body=enquiry.draft.body,
        )
        mailto_url = generate_mailto_url(
            recipient=enquiry.email,
            subject=subject,
            body=enquiry.draft.body,
        )

    return templates.TemplateResponse(
        request=request,
        name="enquiry_detail.html",
        context={
            "enquiry": enquiry,
            "analysis": enquiry.analysis,
            "draft": enquiry.draft,
            "gmail_url": gmail_url,
            "mailto_url": mailto_url,
        },
    )


@router.get("/review", response_class=HTMLResponse, summary="Human review queue")
def view_review_queue(request: Request, db: Session = Depends(get_db)):
    """
    Shows all items needing attention:
    1. Flagged as requires_human_review by AI or category escalation.
    2. Status = NEEDS_REVIEW or FAILED.
    3. Drafts still PENDING review.
    """
    enquiries = (
        db.query(Enquiry)
        .outerjoin(EnquiryAnalysis, Enquiry.id == EnquiryAnalysis.enquiry_id)
        .outerjoin(ResponseDraft, Enquiry.id == ResponseDraft.enquiry_id)
        .filter(
            (Enquiry.processing_status.in_([ProcessingStatus.NEEDS_REVIEW.value, ProcessingStatus.FAILED.value]))
            | (EnquiryAnalysis.requires_human_review == True)
            | (ResponseDraft.approval_status == ApprovalStatus.PENDING.value)
        )
        .distinct()
        .order_by(Enquiry.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "enquiries": enquiries,
        },
    )


# Form-based actions for HTML draft approval / rejection / edit to work without JavaScript
@router.post("/drafts/{draft_id}/action", summary="Handle draft actions from HTML form")
def handle_draft_action(
    draft_id: int,
    action: str = Form(...),
    subject: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timezone
    draft = db.query(ResponseDraft).filter(ResponseDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if subject:
        draft.subject = subject.strip()
    if body:
        draft.body = body.strip()

    if action == "approve":
        draft.approval_status = ApprovalStatus.APPROVED.value
    elif action == "reject":
        draft.approval_status = ApprovalStatus.REJECTED.value
    elif action == "flag":
        draft.approval_status = ApprovalStatus.NEEDS_FOLLOWUP.value
    elif action == "save":
        # Keep current approval_status, just update text
        pass

    draft.updated_at = datetime.now(timezone.utc)
    db.commit()

    return RedirectResponse(
        url=f"/enquiries/{draft.enquiry_id}", status_code=status.HTTP_303_SEE_OTHER
    )
