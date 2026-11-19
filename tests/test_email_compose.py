"""
tests/test_email_compose.py
Unit tests for Gmail and mailto URL generation utilities (Upgrade E).
"""

from urllib.parse import parse_qs, urlparse
from app.utils.email_compose import generate_gmail_compose_url, generate_mailto_url


def test_gmail_url_valid_recipient():
    url = generate_gmail_compose_url(
        recipient="client@example.com",
        subject="Re: Business Enquiry",
        body="Dear Client,\nThank you for reaching out.",
    )
    assert url.startswith("https://mail.google.com/mail/?view=cm&fs=1")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["to"] == ["client@example.com"]
    assert params["su"] == ["Re: Business Enquiry"]
    assert params["body"] == ["Dear Client,\nThank you for reaching out."]


def test_gmail_url_multiline_and_special_chars():
    subject = "Proposal: 100% Quality & AI Automation (Q1)"
    body = "Line 1: Hello!\nLine 2: Budget = $5,000 & 100% discount?\nLine 3: Best,\nCurd Rice"
    url = generate_gmail_compose_url(
        recipient="partner+special@company.org",
        subject=subject,
        body=body,
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["su"] == [subject]
    assert params["body"] == [body]


def test_gmail_url_missing_recipient_handled():
    url = generate_gmail_compose_url(
        recipient=None,
        subject="Draft Subject",
        body="Draft Body",
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert "to" not in params
    assert params["su"] == ["Draft Subject"]
    assert params["body"] == ["Draft Body"]


def test_mailto_url_valid_recipient():
    url = generate_mailto_url(
        recipient="support@example.com",
        subject="Subject Here",
        body="Body with\nmultiple lines.",
    )
    assert url.startswith("mailto:support%40example.com?") or url.startswith("mailto:support@example.com?")
    assert "subject=" in url
    assert "body=" in url


def test_mailto_url_empty_recipient():
    url = generate_mailto_url(
        recipient="",
        subject="General Subject",
        body="General Body",
    )
    assert url.startswith("mailto:?")
    assert "subject=General%20Subject" in url or "subject=General+Subject" in url
