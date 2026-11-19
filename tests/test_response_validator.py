"""
tests/test_response_validator.py
Unit tests for deterministic AI response safety and business policy validator (Upgrade B).
"""

from app.services.response_validator import validate_response_draft


def test_safe_response_passes():
    subject = "Re: Enquiry Regarding Business Automation"
    body = (
        "Dear Rajesh,\n\n"
        "Thank you for contacting Curd Rice Business Studio. We would be happy to learn more "
        "about your requirements. Could we schedule a brief discovery call next week to discuss details?\n\n"
        "Warm regards,\nCurd Rice Business Studio Team"
    )
    res = validate_response_draft(subject, body, category="AI Automation")
    assert res.is_safe is True
    assert res.status == "PASSED"
    assert len(res.issues) == 0
    assert res.requires_human_review is False


def test_invented_pricing_flagged():
    subject = "Re: Web Development Services"
    body = (
        "Dear Ramesh,\n\n"
        "Thank you for reaching out. We can build your e-commerce website for $2,500 only. "
        "Let us schedule a call to finalize this.\n\n"
        "Regards,\nCurd Rice Business Studio Team"
    )
    res = validate_response_draft(subject, body, category="Website Development")
    assert res.is_safe is False
    assert res.status == "FAILED"
    assert any(i.code == "UNAUTHORIZED_PRICING" for i in res.issues)
    assert res.requires_human_review is True


def test_unsupported_guarantee_flagged():
    subject = "Re: Digital Marketing Support"
    body = (
        "Dear Priya,\n\n"
        "We guarantee 100% guarantee that your revenue will triple within 30 days. "
        "Let us connect to start.\n\n"
        "Regards,\nCurd Rice Business Studio Team"
    )
    res = validate_response_draft(subject, body, category="Branding and Marketing")
    assert res.is_safe is False
    assert res.status == "FAILED"
    assert any(i.code == "UNSUPPORTED_GUARANTEE" for i in res.issues)
    assert res.requires_human_review is True


def test_delivery_date_commitment_flagged():
    subject = "Re: ERP Implementation"
    body = (
        "Dear Sunil,\n\n"
        "We will deliver by next Monday and the platform is guaranteed completion by Friday. "
        "Let us discuss the scope.\n\n"
        "Regards,\nCurd Rice Business Studio Team"
    )
    res = validate_response_draft(subject, body, category="Application Development")
    assert res.is_safe is False
    assert res.status == "FAILED"
    assert any(i.code == "UNAUTHORIZED_TIMELINE_COMMITMENT" for i in res.issues)
    assert res.requires_human_review is True


def test_complaint_dismissive_tone_flagged():
    subject = "Re: Service Issue"
    body = (
        "Hello Customer,\n\n"
        "This is not our fault and there is nothing we can do about your previous invoice.\n\n"
        "Regards,\nCurd Rice Business Studio Team"
    )
    res = validate_response_draft(subject, body, category="Complaint")
    assert res.is_safe is False
    assert res.status == "FAILED"
    assert any(i.code == "INAPPROPRIATE_COMPLAINT_TONE" for i in res.issues)


def test_missing_greeting_detected():
    subject = "Re: Project Inquiry"
    body = (
        "Thank you for contacting Curd Rice Business Studio. We would like to discuss next steps.\n\n"
        "Regards,\nCurd Rice Business Studio Team"
    )
    res = validate_response_draft(subject, body, category="Business Consulting")
    assert any(i.code == "MISSING_GREETING" for i in res.issues)


def test_multiple_issues_flagged():
    subject = "Re: Project Deal"
    body = (
        "We promise you that the price is $5,000 and we will deliver by next week without charge."
    )
    res = validate_response_draft(subject, body, category="AI Automation")
    assert res.is_safe is False
    assert res.status == "FAILED"
    assert len(res.issues) >= 3
    issue_codes = {i.code for i in res.issues}
    assert "UNAUTHORIZED_PRICING" in issue_codes
    assert "UNSUPPORTED_GUARANTEE" in issue_codes
    assert "MISSING_GREETING" in issue_codes
