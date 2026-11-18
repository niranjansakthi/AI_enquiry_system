"""
tests/test_lead_scoring.py
──────────────────────────
Unit tests for deterministic Python lead scoring (Module C).
Tests all 5 dimensions, priority classifications, boundary limits, and edge cases.
"""

from app.services.lead_scoring import calculate_lead_score
from schemas import ExtractedInfo


def test_high_priority_lead():
    info = ExtractedInfo(
        category="AI Automation",
        requirement="Need AI automation for handling 500 customer enquiries per day across WhatsApp and CRM.",
        budget="5 lakh",
        expected_timeline="immediately",
        confidence=0.95,
        requires_human_review=False,
    )
    res = calculate_lead_score(info)
    assert res.score >= 70
    assert res.priority == "High"
    assert len(res.reasons) == 5
    assert any("Specific budget" in r for r in res.reasons)
    assert any("Urgent" in r for r in res.reasons)


def test_medium_priority_lead():
    info = ExtractedInfo(
        category="Website Development",
        requirement="Need a website for our manufacturing company.",
        budget="2 lakh",
        expected_timeline="this week",
        confidence=0.85,
        requires_human_review=False,
    )
    res = calculate_lead_score(info)
    assert 40 <= res.score <= 100
    assert res.priority in ("High", "Medium")


def test_low_priority_generic_enquiry():
    info = ExtractedInfo(
        category="General Enquiry",
        requirement="What services do you offer?",
        budget=None,
        expected_timeline=None,
        confidence=0.7,
        requires_human_review=False,
    )
    res = calculate_lead_score(info)
    assert res.score < 40
    assert res.priority == "Low"
    assert any("No budget" in r for r in res.reasons)
    assert any("No timeline" in r for r in res.reasons)


def test_complaint_scoring():
    info = ExtractedInfo(
        category="Complaint",
        requirement="Unhappy with service received, call urgently",
        budget=None,
        expected_timeline="urgently",
        confidence=0.98,
        requires_human_review=True,
        review_reason="Complaint",
    )
    res = calculate_lead_score(info)
    # Numerical score reflects low commercial intent
    assert res.score < 50
    assert res.priority in ("Low", "Medium")


def test_empty_fields_handling():
    info = ExtractedInfo(
        category="Other",
        requirement=None,
        budget=None,
        expected_timeline=None,
        confidence=0.5,
        requires_human_review=False,
    )
    res = calculate_lead_score(info)
    assert res.score <= 20
    assert res.priority == "Low"


def test_score_never_exceeds_100():
    info = ExtractedInfo(
        category="AI Automation",
        requirement="Extremely long detailed requirement with ERP, CRM, WhatsApp integration to handle 1000 orders per day and automate end-to-end dispatch and customer service.",
        budget="10,00,000 INR",
        expected_timeline="immediately",
        confidence=1.0,
        requires_human_review=False,
    )
    res = calculate_lead_score(info)
    assert res.score <= 100
    assert res.priority == "High"

