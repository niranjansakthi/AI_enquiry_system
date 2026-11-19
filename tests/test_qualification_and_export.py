"""
tests/test_qualification_and_export.py
Unit tests for Smart Lead Qualification (Upgrade C) and CSV Batch Export (Upgrade D).
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.qualification import analyze_lead_qualification
from app.utils.csv_processor import export_enquiries_to_csv
from models import Enquiry, EnquiryAnalysis, ResponseDraft, ProcessingStatus
from schemas import ExtractedInfo


def test_smart_qualification_identifies_missing_and_available():
    # Customer provides budget & requirement, but no company and no timeline
    info = ExtractedInfo(
        category="AI Automation",
        customer_name="Arjun",
        company_name=None,
        email="arjun@test.com",
        requirement="We need an AI customer chatbot for our retail sales orders.",
        budget="2 Lakhs",
        expected_timeline=None,
        intent="Chatbot integration",
        confidence=0.92,
        requires_human_review=False,
    )
    res = analyze_lead_qualification(
        message="We need an AI customer chatbot for our retail sales orders with 2 Lakhs budget.",
        extracted=info,
        customer_name="Arjun",
        company_name=None,
    )
    assert any("Budget" in a for a in res.available_info)
    assert any("Core Requirement" in a for a in res.available_info)
    assert any("Company" in m for m in res.missing_info)
    assert any("Timeline" in m for m in res.missing_info)
    assert len(res.clarification_questions) >= 1
    assert "Hi Arjun" in res.follow_up_draft


def test_smart_qualification_for_complaint():
    info = ExtractedInfo(
        category="Complaint",
        customer_name="Sanjay",
        company_name="Apex Logistics",
        email="sanjay@test.com",
        requirement="Deliveries delayed without explanation.",
        budget=None,
        expected_timeline=None,
        intent="Resolve dispute",
        confidence=0.98,
        requires_human_review=True,
    )
    res = analyze_lead_qualification(
        message="Deliveries delayed without explanation.",
        extracted=info,
        customer_name="Sanjay",
        company_name="Apex Logistics",
    )
    # Shouldn't ask for project budget in a complaint
    assert not any("budget range" in q.lower() for q in res.clarification_questions)
    # Should ask for order or invoice reference
    assert any("invoice" in q.lower() or "order" in q.lower() for q in res.clarification_questions)


def test_csv_export_utility(db_session: Session):
    enquiry = Enquiry(
        customer_name="Karthik",
        company_name="Karthik Silks",
        email="karthik@silks.com",
        message="Need automated catalog updates and inventory management.",
        source="csv_upload",
        processing_status=ProcessingStatus.COMPLETED.value,
        is_duplicate=False,
    )
    db_session.add(enquiry)
    db_session.commit()
    db_session.refresh(enquiry)

    analysis = EnquiryAnalysis(
        enquiry_id=enquiry.id,
        category="AI Automation",
        requirement="Automated catalog updates",
        budget="1.5 Lakh",
        expected_timeline="1 month",
        intent="Inventory automation",
        confidence=0.94,
        lead_score=85,
        priority="High",
        scoring_reasons='["Direct business match", "Specific budget"]',
        qualification_missing_info='["Expected volume"]',
        clarification_questions='["How many SKU items do you maintain?"]',
        requires_human_review=False,
    )
    draft = ResponseDraft(
        enquiry_id=enquiry.id,
        subject="Re: Catalog Automation",
        body="Dear Karthik, thank you for reaching out.",
        approval_status="APPROVED",
        validation_status="PASSED",
        validation_issues="[]",
    )
    db_session.add(analysis)
    db_session.add(draft)
    db_session.commit()

    csv_output = export_enquiries_to_csv([enquiry])
    assert "Enquiry ID,Customer Name,Company,Email" in csv_output
    assert "Karthik,Karthik Silks,karthik@silks.com" in csv_output
    assert "AI Automation,85,High" in csv_output
    assert "Re: Catalog Automation" in csv_output
    assert "PASSED" in csv_output


def test_export_csv_endpoint(client: TestClient):
    res = client.get("/enquiries/export-csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "Enquiry ID,Customer Name,Company" in res.text
