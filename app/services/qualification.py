"""Lead qualification and clarification question generator."""

from typing import Optional

from schemas import ExtractedInfo, QualificationResult


def analyze_lead_qualification(
    message: str,
    extracted: ExtractedInfo,
    customer_name: Optional[str] = None,
    company_name: Optional[str] = None,
) -> QualificationResult:
    """
    Evaluates what crucial qualification data is present vs missing,
    and formulates concise, context-aware clarification questions.
    """
    category = extracted.category or "General Enquiry"
    msg_lower = message.lower()

    available: list[str] = []
    missing: list[str] = []
    questions: list[str] = []

    # 1. Contact / Organization identity
    has_company = bool(company_name or extracted.company_name)
    if has_company:
        available.append("Business / Company Name")
    else:
        missing.append("Company or Industry Domain")
        questions.append("Could you share a bit more about your company and current industry?")

    # 2. Scope & Technical Requirements
    if extracted.requirement and len(extracted.requirement.strip()) >= 25:
        available.append("Core Requirement Summary")
    else:
        missing.append("Detailed Functional Requirements")
        if category == "AI Automation":
            questions.append("What specific workflows or customer touchpoints (e.g., WhatsApp, CRM, website) do you plan to automate?")
        elif category in {"Website Development", "Application Development"}:
            questions.append("Do you have existing wireframes, design references, or technical platform preferences?")
        else:
            questions.append("What are the primary operational challenges or features you would like to address?")

    # 3. Budget
    if extracted.budget:
        available.append(f"Budget Mentioned ({extracted.budget})")
    else:
        missing.append("Budget Range or Allocation")
        if category not in {"Complaint", "Job and Internship Application"}:
            questions.append("Do you have a target budget range or investment bracket in mind for this project?")

    # 4. Timeline
    if extracted.expected_timeline:
        available.append(f"Timeline Indicated ({extracted.expected_timeline})")
    else:
        missing.append("Desired Timeline or Launch Date")
        if category not in {"Complaint", "Job and Internship Application"}:
            questions.append("What is your expected timeline for commencing or going live with this initiative?")

    # 5. Category-Specific Scale / Volume Check
    if category == "AI Automation":
        has_volume = any(w in msg_lower for w in ["volume", "orders", "users", "chats", "tickets", "messages", "per day", "per month"])
        if has_volume:
            available.append("Estimated User / Enquiry Volume")
        else:
            missing.append("Expected Monthly Message or Transaction Volume")
            questions.append("Approximately how many daily or monthly customer conversations or requests do you anticipate handling?")

    elif category == "Complaint":
        has_ref = any(w in msg_lower for w in ["invoice", "order", "ticket", "#", "ref", "id", "account"])
        if has_ref:
            available.append("Incident Reference / Order Details")
        else:
            missing.append("Order / Invoice / Account Reference")
            questions.append("Could you provide your invoice number, order ID, or account details so we can investigate immediately?")

    elif category == "Job and Internship Application":
        has_portfolio = any(w in msg_lower for w in ["resume", "cv", "portfolio", "github", "linkedin", "link"])
        if has_portfolio:
            available.append("Resume / Portfolio Mention")
        else:
            missing.append("Resume or Portfolio Link")
            questions.append("Could you share your updated resume, GitHub profile, or portfolio link?")

    # Limit questions to top 3 to keep communication professional and not overwhelming
    selected_questions = questions[:3]

    # Optional follow-up email draft segment
    greeting_name = customer_name or extracted.customer_name or "there"
    follow_up_lines = [
        f"Hi {greeting_name},",
        "",
        "Thank you for sharing your enquiry with Curd Rice Business Studio.",
        "To help our technical team prepare an accurate assessment and tailor the right solution for you, could you please clarify the following points?",
        "",
    ]
    for i, q in enumerate(selected_questions, 1):
        follow_up_lines.append(f"{i}. {q}")
    follow_up_lines.extend([
        "",
        "Looking forward to hearing from you.",
        "",
        "Warm regards,",
        "Curd Rice Business Studio Team",
    ])
    follow_up_draft = "\n".join(follow_up_lines)

    return QualificationResult(
        available_info=available,
        missing_info=missing,
        clarification_questions=selected_questions,
        follow_up_draft=follow_up_draft,
    )
