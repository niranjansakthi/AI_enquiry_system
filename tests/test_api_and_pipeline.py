"""
tests/test_api_and_pipeline.py
───────────────────────────────
Integration tests for REST API endpoints and pipeline processing.
Uses mocked Groq responses to run fast and deterministically without consuming API tokens.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from schemas import ExtractedInfo, DraftContent
from models import Enquiry, EnquiryAnalysis, ResponseDraft, ApprovalStatus, ProcessingStatus


@pytest.fixture
def mock_ai_services():
    mock_extracted = ExtractedInfo(
        category="AI Automation",
        customer_name="Sunil",
        company_name="Jewellery Hub",
        email="sunil@example.com",
        requirement="AI-powered WhatsApp customer support system",
        budget="1 Lakh",
        expected_timeline="immediately",
        intent="Service enquiry",
        confidence=0.92,
        requires_human_review=False,
    )
    mock_draft = DraftContent(
        subject="Re: AI WhatsApp Customer Support Enquiry",
        body="Dear Sunil,\n\nThank you for reaching out to Curd Rice Business Studio...",
    )

    with patch("app.services.ai_understanding.extract_enquiry_info", return_value=mock_extracted), \
         patch("app.services.ai_response.generate_email_draft", return_value=mock_draft):
        yield mock_extracted, mock_draft


def test_submit_enquiry_api(client: TestClient, mock_ai_services):
    payload = {
        "customer_name": "Sunil",
        "company_name": "Jewellery Hub",
        "email": "sunil@example.com",
        "message": "We are a jewellery business looking for an AI-powered WhatsApp customer support system.",
        "source": "api"
    }
    response = client.post("/api/enquiries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["enquiry"]["id"] is not None
    assert data["enquiry"]["processing_status"] in ("COMPLETED", "NEEDS_REVIEW")
    assert data["analysis"]["category"] == "AI Automation"
    assert data["analysis"]["lead_score"] >= 70
    assert data["draft"]["subject"] == "Re: AI WhatsApp Customer Support Enquiry"


def test_complaint_escalation_in_pipeline(client: TestClient):
    mock_complaint = ExtractedInfo(
        category="Complaint",
        customer_name="Angry Client",
        company_name=None,
        email="angry@example.com",
        requirement="Unhappy with service, urgent callback needed",
        budget=None,
        expected_timeline="urgently",
        intent="Complaint resolution",
        confidence=0.99,
        requires_human_review=True,
        review_reason="Customer expressed dissatisfaction and urgent escalation.",
    )
    mock_draft = DraftContent(
        subject="Re: Urgent Follow-up Regarding Your Experience",
        body="Dear Customer,\n\nWe sincerely apologise for any inconvenience caused...",
    )

    with patch("app.services.ai_understanding.extract_enquiry_info", return_value=mock_complaint), \
         patch("app.services.ai_response.generate_email_draft", return_value=mock_draft):
        payload = {
            "message": "I am unhappy with the service received and need someone to call me urgently.",
            "source": "api"
        }
        res = client.post("/api/enquiries", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["enquiry"]["processing_status"] == "NEEDS_REVIEW"
        assert data["analysis"]["requires_human_review"] is True
        assert data["analysis"]["review_reason"] == "Customer expressed dissatisfaction and urgent escalation."


def test_draft_approval_workflow(client: TestClient, mock_ai_services):
    # 1. Create enquiry
    res = client.post("/api/enquiries", json={
        "message": "Need ERP software for our manufacturing workshop.",
        "source": "api"
    })
    enquiry_id = res.json()["enquiry"]["id"]
    draft_id = res.json()["draft"]["id"]

    # 2. Edit draft
    update_res = client.put(f"/api/drafts/{draft_id}", json={
        "subject": "Updated Custom Subject Line",
        "body": "Updated body text crafted by reviewer."
    })
    assert update_res.status_code == 200
    assert update_res.json()["subject"] == "Updated Custom Subject Line"

    # 3. Approve draft
    appr_res = client.post(f"/api/drafts/{draft_id}/approve")
    assert appr_res.status_code == 200
    assert appr_res.json()["success"] is True

    # 4. Verify in GET
    detail_res = client.get(f"/api/enquiries/{enquiry_id}")
    assert detail_res.json()["draft"]["approval_status"] == "APPROVED"


def test_draft_rejection(client: TestClient, mock_ai_services):
    res = client.post("/api/enquiries", json={
        "message": "Looking for marketing partnership.",
        "source": "api"
    })
    draft_id = res.json()["draft"]["id"]

    rej_res = client.post(f"/api/drafts/{draft_id}/reject")
    assert rej_res.status_code == 200
    assert rej_res.json()["success"] is True


def test_csv_upload_endpoint(client: TestClient, mock_ai_services):
    csv_content = b"customer_name,company_name,email,message,source\nJohn,Acme,john@acme.com,Automate inventory and dispatch operations,csv_upload\n"
    response = client.post(
        "/api/enquiries/upload-csv",
        files={"file": ("test.csv", csv_content, "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    assert data["failed"] == 0
    assert len(data["results"]) == 1


def test_dashboard_stats_api(client: TestClient, mock_ai_services):
    client.post("/api/enquiries", json={"message": "Inquire about consulting services", "source": "api"})
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["total_enquiries"] >= 1
    assert "priority" in stats
    assert "status" in stats
