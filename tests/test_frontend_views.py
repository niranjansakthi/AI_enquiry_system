"""
tests/test_frontend_views.py
─────────────────────────────
Automated verification for all server-rendered HTML views.
"""

import io
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from schemas import DraftContent, ExtractedInfo, LeadScore


def test_all_pages_return_200(client: TestClient):
    """Verify all HTML endpoints return 200 OK and expected HTML content."""
    urls = [
        ("/", "Business Enquiry Dashboard"),
        ("/enquiries", "Enquiry Management"),
        ("/enquiries/new", "Manual Enquiry Submission"),
        ("/upload-csv", "Upload Enquiry CSV"),
        ("/analytics", "Lead Analytics"),
        ("/review", "Human Review Queue"),
        ("/about", "About Curd Rice Business Studio"),
    ]
    for url, expected_text in urls:
        resp = client.get(url)
        assert resp.status_code == 200, f"Expected 200 for {url}, got {resp.status_code}"
        assert expected_text in resp.text, f"Expected '{expected_text}' in response for {url}"


def test_new_enquiry_form_submission_flow(client: TestClient):
    """Test manual enquiry form POST /enquiries/new."""
    mock_info = ExtractedInfo(
        category="AI Automation",
        customer_name="Priya Sharma",
        company_name="Apex Logistics",
        email="priya@apex.in",
        requirement="Automate order notifications",
        budget="INR 2,00,000",
        expected_timeline="1 month",
        intent="Business automation",
        confidence=0.92,
        requires_human_review=False,
    )
    mock_score = LeadScore(
        score=75,
        priority="High",
        reasons=["Direct business match", "High budget provided"],
    )
    mock_draft = DraftContent(
        subject="Regarding your automation inquiry - Curd Rice Studio",
        body="Dear Priya, thank you for reaching out.",
    )

    with patch("app.services.ai_understanding.extract_enquiry_info", return_value=mock_info), \
         patch("app.services.lead_scoring.calculate_lead_score", return_value=mock_score), \
         patch("app.services.ai_response.generate_email_draft", return_value=mock_draft):

        form_data = {
            "customer_name": "Priya Sharma",
            "company_name": "Apex Logistics",
            "email": "priya@apex.in",
            "message": "We need automated WhatsApp notifications for dispatches.",
        }
        # follow_redirects=False to verify 303 redirect
        resp = client.post("/enquiries/new", data=form_data, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/enquiries/")

        # Follow redirect to view the newly created enquiry
        detail_resp = client.get(resp.headers["location"])
        assert detail_resp.status_code == 200
        assert "Priya Sharma" in detail_resp.text
        assert "Apex Logistics" in detail_resp.text


def test_upload_csv_html_form_flow(client: TestClient):
    """Test CSV upload through HTML form POST /upload-csv."""
    mock_info = ExtractedInfo(
        category="Website Development",
        customer_name="Rajesh Patel",
        company_name="Patel Spices",
        email="rajesh@patelspices.com",
        requirement="Redesign e-commerce website",
        budget="INR 1,50,000",
        expected_timeline="2 months",
        intent="Website upgrade",
        confidence=0.95,
        requires_human_review=False,
    )
    mock_score = LeadScore(
        score=70,
        priority="High",
        reasons=["Strong website scope", "Budget stated"],
    )
    mock_draft = DraftContent(
        subject="Regarding your website project",
        body="Dear Rajesh, we can help build your website.",
    )

    csv_data = (
        "customer_name,company_name,email,message\n"
        "Rajesh Patel,Patel Spices,rajesh@patelspices.com,Need new e-commerce store with checkout.\n"
    )

    with patch("app.services.ai_understanding.extract_enquiry_info", return_value=mock_info), \
         patch("app.services.lead_scoring.calculate_lead_score", return_value=mock_score), \
         patch("app.services.ai_response.generate_email_draft", return_value=mock_draft):

        files = {"file": ("test_leads.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        resp = client.post("/upload-csv", files=files)
        assert resp.status_code == 200
        assert "Batch Processing Complete!" in resp.text
        assert "Processed Enquiries" in resp.text
        assert "Rajesh Patel" in resp.text
        assert "Website Development" in resp.text
