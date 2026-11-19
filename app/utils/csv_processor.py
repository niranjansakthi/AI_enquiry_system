"""
app/utils/csv_processor.py
───────────────────────────
Reads an uploaded CSV file and yields EnquiryCreate rows.

Supported CSV columns (case-insensitive, all optional except message):
  customer_name, company_name, email, message, source

Rows that fail validation are collected as errors and returned alongside
the valid rows so the caller can report them without stopping the batch.
"""

import csv
import io
import logging
from typing import Optional

from pydantic import ValidationError

from schemas import EnquiryCreate
from app.utils.validators import clean_optional_str, is_valid_email

logger = logging.getLogger(__name__)

# Maps common alternative column header names to the canonical field names
COLUMN_ALIASES: dict[str, str] = {
    "name": "customer_name",
    "customer": "customer_name",
    "contact_name": "customer_name",
    "company": "company_name",
    "organisation": "company_name",
    "organization": "company_name",
    "email_address": "email",
    "enquiry": "message",
    "enquiry_message": "message",
    "query": "message",
    "message_text": "message",
}


def _normalise_header(header: str) -> str:
    """Lowercase and strip a column header, then resolve aliases."""
    normalised = header.strip().lower().replace(" ", "_")
    return COLUMN_ALIASES.get(normalised, normalised)


def parse_csv(
    content: bytes,
) -> tuple[list[EnquiryCreate], list[dict]]:
    """
    Parse CSV bytes into a list of EnquiryCreate objects.

    Args:
        content : raw bytes from the uploaded file

    Returns:
        (valid_rows, errors)
        valid_rows : list of EnquiryCreate objects ready to process
        errors     : list of dicts describing rows that failed validation
    """
    valid_rows: list[EnquiryCreate] = []
    errors: list[dict] = []

    try:
        text = content.decode("utf-8-sig")  # handles BOM from Excel exports
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return [], [{"row": 0, "error": "CSV file has no header row or is empty."}]

    # Normalise headers
    normalised_headers = {h: _normalise_header(h) for h in reader.fieldnames}

    for i, raw_row in enumerate(reader, start=2):  # row 1 is the header
        # Remap headers
        row: dict[str, Optional[str]] = {
            normalised_headers[k]: v for k, v in raw_row.items()
        }

        message = clean_optional_str(row.get("message"))
        if not message:
            errors.append({"row": i, "error": "Missing required 'message' column."})
            continue

        email = clean_optional_str(row.get("email"))
        if email and not is_valid_email(email):
            logger.warning("Row %d: invalid email '%s' — set to null.", i, email)
            email = None  # Don't reject the row, just drop the bad email

        source = clean_optional_str(row.get("source")) or "csv_upload"
        if source not in {"web_form", "api", "csv_upload"}:
            source = "csv_upload"

        try:
            enquiry = EnquiryCreate(
                customer_name=clean_optional_str(row.get("customer_name")),
                company_name=clean_optional_str(row.get("company_name")),
                email=email,
                message=message,
                source=source,
            )
            valid_rows.append(enquiry)
        except ValidationError as exc:
            errors.append({"row": i, "error": str(exc.errors()[0]["msg"])})

    logger.info(
        "CSV parsed: %d valid rows, %d errors.", len(valid_rows), len(errors)
    )
    return valid_rows, errors


def export_enquiries_to_csv(enquiries: list) -> str:
    """
    Generate a CSV export containing all available enquiry, analysis,
    qualification, and response draft data.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "Enquiry ID",
        "Customer Name",
        "Company",
        "Email",
        "Original Enquiry",
        "Service Category",
        "Lead Score",
        "Priority",
        "Score Explanation",
        "Missing Qualification Information",
        "Suggested Clarification Questions",
        "Draft Subject",
        "Draft Response Body",
        "Draft Approval Status",
        "Validation Status",
        "Validation Issues",
        "Processing Status",
        "Potential Duplicate",
        "Duplicate Of ID",
        "Submission Date",
    ]
    writer.writerow(headers)

    for enq in enquiries:
        analysis = enq.analysis
        draft = enq.draft

        scoring_reasons_str = "; ".join(analysis.scoring_reasons_list) if analysis else ""
        missing_info_str = "; ".join(analysis.qualification_missing_info_list) if analysis else ""
        clarification_str = " | ".join(analysis.clarification_questions_list) if analysis else ""
        validation_issues_str = "; ".join(draft.validation_issues_list) if draft else ""

        created_str = (
            enq.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if enq.created_at
            else ""
        )

        row = [
            f"EQ-{enq.id:03d}",
            enq.customer_name or "",
            enq.company_name or "",
            enq.email or "",
            enq.message or "",
            (analysis.category if analysis else "") or "",
            analysis.lead_score if (analysis and analysis.lead_score is not None) else "",
            (analysis.priority if analysis else "") or "",
            scoring_reasons_str,
            missing_info_str,
            clarification_str,
            (draft.subject if draft else "") or "",
            (draft.body if draft else "") or "",
            (draft.approval_status if draft else "") or "",
            (draft.validation_status if draft else "") or "",
            validation_issues_str,
            enq.processing_status or "",
            "Yes" if enq.is_duplicate else "No",
            f"EQ-{enq.duplicate_of_id:03d}" if enq.duplicate_of_id else "",
            created_str,
        ]
        writer.writerow(row)

    return output.getvalue()


