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

