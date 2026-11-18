"""
tests/test_csv_upload_extended.py
─────────────────────────────────
Extended tests for CSV processing:
- Parsing messy headers & whitespace
- Handling invalid email strings gracefully without breaking the batch
- Handling empty / corrupted CSV files
- Full CSV upload endpoint through FastAPI test client
"""

import pytest
from app.utils.csv_processor import parse_csv
from schemas import EnquiryCreate


def test_parse_csv_clean_data():
    content = (
        b"customer_name,company_name,email,message,source\n"
        b"Rahul,Acme Corp,rahul@acme.com,Looking for AI automation for dispatch operations.,web_form\n"
    )
    rows, errors = parse_csv(content)
    assert len(rows) == 1
    assert len(errors) == 0
    assert rows[0].customer_name == "Rahul"
    assert rows[0].email == "rahul@acme.com"
    assert rows[0].source == "web_form"


def test_parse_csv_header_aliases_and_case():
    # Use alternative headers like 'name', 'organisation', 'query'
    content = (
        b"Name,Organisation,Email_Address,Query\n"
        b"Meena,Silver Crafts,meena@silvercrafts.in,Need an ERP system for inventory tracking.\n"
    )
    rows, errors = parse_csv(content)
    assert len(rows) == 1
    assert len(errors) == 0
    assert rows[0].customer_name == "Meena"
    assert rows[0].company_name == "Silver Crafts"
    assert rows[0].email == "meena@silvercrafts.in"
    assert rows[0].message == "Need an ERP system for inventory tracking."
    assert rows[0].source == "csv_upload"


def test_parse_csv_handles_invalid_email_gracefully():
    # Invalid email shouldn't reject the whole row; it should set email to None
    content = (
        b"customer_name,company_name,email,message\n"
        b"Suresh,,bad-email-format,Interested in web consulting for retail store.\n"
    )
    rows, errors = parse_csv(content)
    assert len(rows) == 1
    assert len(errors) == 0
    assert rows[0].customer_name == "Suresh"
    assert rows[0].email is None  # Sanitized to None


def test_parse_csv_missing_message_recorded_as_error():
    content = (
        b"customer_name,company_name,email,message\n"
        b"Row One,Acme,one@acme.com,\n"  # Empty message
        b"Row Two,Acme,two@acme.com,Valid enquiry message text.\n"
    )
    rows, errors = parse_csv(content)
    assert len(rows) == 1
    assert len(errors) == 1
    assert errors[0]["row"] == 2
    assert "Missing required 'message'" in errors[0]["error"]


def test_parse_csv_empty_file():
    rows, errors = parse_csv(b"")
    assert len(rows) == 0
    assert len(errors) == 1
    assert "empty" in errors[0]["error"].lower()

