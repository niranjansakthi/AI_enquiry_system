"""
tests/test_duplicate_detection.py
Unit tests for deterministic duplicate enquiry detection (Upgrade A).
"""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session

from app.services.duplicate_detection import (
    calculate_text_similarity,
    check_duplicate_enquiry,
    normalize_email,
    normalize_text,
)
from models import Enquiry, ProcessingStatus


def test_normalize_email():
    assert normalize_email("  User@Example.COM  ") == "user@example.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_normalize_text():
    text = "Hello!! We want an ERP... System,   now. "
    normalized = normalize_text(text)
    assert normalized == "hello we want an erp system now"


def test_calculate_text_similarity():
    t1 = "Need AI chatbot for WhatsApp customer support."
    t2 = "Need AI chatbot for WhatsApp customer support system."
    similarity = calculate_text_similarity(t1, t2)
    assert similarity > 0.85

    t3 = "Looking for website development services."
    assert calculate_text_similarity(t1, t3) < 0.4


def test_exact_duplicate_detected(db_session: Session):
    # Existing enquiry submitted 2 days ago
    past_date = datetime.now(timezone.utc) - timedelta(days=2)
    existing = Enquiry(
        customer_name="Ramesh",
        email="ramesh@test.com",
        message="Looking for an ERP system for inventory tracking.",
        source="api",
        processing_status=ProcessingStatus.COMPLETED.value,
        created_at=past_date,
    )
    db_session.add(existing)
    db_session.commit()

    # Identical submission today
    result = check_duplicate_enquiry(
        email="ramesh@test.com",
        message="Looking for an ERP system for inventory tracking.",
        db=db_session,
        window_days=7,
    )
    assert result.is_duplicate is True
    assert result.original_enquiry_id == existing.id
    assert "Exact duplicate detected" in result.message


def test_same_email_different_capitalization(db_session: Session):
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    existing = Enquiry(
        customer_name="Anita",
        email="anita@test.com",
        message="Need automated dispatch alerts.",
        source="web_form",
        processing_status=ProcessingStatus.COMPLETED.value,
        created_at=past_date,
    )
    db_session.add(existing)
    db_session.commit()

    # Submission with capitalized email
    result = check_duplicate_enquiry(
        email="  ANITA@TEST.COM ",
        message="Need automated dispatch alerts.",
        db=db_session,
        window_days=7,
    )
    assert result.is_duplicate is True
    assert result.original_enquiry_id == existing.id


def test_near_duplicate_detected(db_session: Session):
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    existing = Enquiry(
        customer_name="Vikram",
        email="vikram@test.com",
        message="We are interested in an AI chatbot for WhatsApp customer support.",
        source="api",
        processing_status=ProcessingStatus.COMPLETED.value,
        created_at=past_date,
    )
    db_session.add(existing)
    db_session.commit()

    # Similar variation
    result = check_duplicate_enquiry(
        email="vikram@test.com",
        message="Interested in an AI chatbot for our WhatsApp customer support system.",
        db=db_session,
        window_days=7,
        threshold=0.80,
    )
    assert result.is_duplicate is True
    assert result.original_enquiry_id == existing.id
    assert "Potential duplicate detected" in result.message


def test_unrelated_enquiry_from_same_customer_not_flagged(db_session: Session):
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    existing = Enquiry(
        customer_name="Kiran",
        email="kiran@test.com",
        message="Need an ERP system for warehouse and stock management.",
        source="api",
        processing_status=ProcessingStatus.COMPLETED.value,
        created_at=past_date,
    )
    db_session.add(existing)
    db_session.commit()

    # Totally different service request
    result = check_duplicate_enquiry(
        email="kiran@test.com",
        message="We also want to redesign our branding and marketing brochures.",
        db=db_session,
        window_days=7,
    )
    assert result.is_duplicate is False


def test_enquiry_outside_window_not_flagged(db_session: Session):
    # Submitted 15 days ago (outside 7 day window)
    past_date = datetime.now(timezone.utc) - timedelta(days=15)
    existing = Enquiry(
        customer_name="Deepak",
        email="deepak@test.com",
        message="Looking for consulting on retail systems.",
        source="api",
        processing_status=ProcessingStatus.COMPLETED.value,
        created_at=past_date,
    )
    db_session.add(existing)
    db_session.commit()

    result = check_duplicate_enquiry(
        email="deepak@test.com",
        message="Looking for consulting on retail systems.",
        db=db_session,
        window_days=7,
    )
    assert result.is_duplicate is False


def test_missing_email_duplicate_detected(db_session: Session):
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    existing = Enquiry(
        customer_name=None,
        email=None,
        message="Anonymous enquiry asking for retail point-of-sale software integration.",
        source="web_form",
        processing_status=ProcessingStatus.COMPLETED.value,
        created_at=past_date,
    )
    db_session.add(existing)
    db_session.commit()

    result = check_duplicate_enquiry(
        email=None,
        message="Anonymous enquiry asking for retail point-of-sale software integration.",
        db=db_session,
        window_days=7,
    )
    assert result.is_duplicate is True
    assert result.original_enquiry_id == existing.id
