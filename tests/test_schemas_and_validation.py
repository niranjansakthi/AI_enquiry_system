"""
tests/test_schemas_and_validation.py
───────────────────────────────────
Unit tests for Pydantic input/output schemas and data validation helpers.
"""

import pytest
from pydantic import ValidationError

from app.utils.validators import is_valid_email, clean_optional_str, sanitise_message
from schemas import EnquiryCreate, ExtractedInfo, DraftUpdate


def test_valid_enquiry_create():
    enq = EnquiryCreate(
        customer_name="  Alice  ",
        company_name="Acme Inc",
        email="alice@acme.com",
        message="Need an ERP solution for jewellery tracking.",
        source="web_form",
    )
    assert enq.customer_name == "Alice"
    assert enq.source == "web_form"


def test_missing_optional_fields_allowed():
    enq = EnquiryCreate(
        message="What are your standard business intelligence services?",
    )
    assert enq.customer_name is None
    assert enq.company_name is None
    assert enq.email is None
    assert enq.source == "api"


def test_invalid_email_raises_error():
    with pytest.raises(ValidationError):
        EnquiryCreate(
            email="not-an-email",
            message="Test message with bad email address.",
        )


def test_message_too_short_raises_error():
    with pytest.raises(ValidationError):
        EnquiryCreate(message="hi")


def test_invalid_source_raises_error():
    with pytest.raises(ValidationError):
        EnquiryCreate(
            message="Valid message text here.",
            source="unsupported_source",
        )


def test_extracted_info_category_coercion():
    info = ExtractedInfo(
        category="NonExistentCategory",
        confidence=0.8,
    )
    assert info.category == "Other"


def test_draft_update_validation():
    # At least one field required
    with pytest.raises(ValidationError):
        DraftUpdate()

    update = DraftUpdate(subject="New subject")
    assert update.subject == "New subject"
    assert update.body is None


def test_validator_helpers():
    assert is_valid_email("test@example.com") is True
    assert is_valid_email("invalid-email") is False
    assert clean_optional_str("   ") is None
    assert clean_optional_str("  valid  ") == "valid"
    assert sanitise_message("line 1\n\n\n\nline 2") == "line 1\n\nline 2"

