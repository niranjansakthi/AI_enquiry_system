"""Rule-based lead scoring across 5 evaluation dimensions."""

import logging
import re

from schemas import ExtractedInfo, LeadScore

logger = logging.getLogger(__name__)

# Dimension 1: Business relevance
CATEGORY_RELEVANCE: dict[str, int] = {
    "AI Automation": 30,            # Core offering
    "Application Development": 28,  # Core offering
    "Website Development": 25,      # Core offering
    "Business Consulting": 22,      # Core offering
    "Branding and Marketing": 18,   # Supported service
    "General Enquiry": 10,          # May convert; too early to judge
    "Partnership": 8,               # Non-standard; needs human evaluation
    "Job and Internship Application": 5,  # Not a business enquiry
    "Complaint": 5,                 # Requires resolution, not sales
    "Other": 8,                     # Unknown; conservative score
}


def _score_business_relevance(category: str) -> tuple[int, str]:
    points = CATEGORY_RELEVANCE.get(category, 8)
    if points >= 25:
        reason = f"Strong category match: '{category}' aligns with core services."
    elif points >= 15:
        reason = f"Moderate category match: '{category}' is a supported service."
    elif points >= 8:
        reason = f"Weak category match: '{category}' has limited direct business value."
    else:
        reason = f"Low relevance: '{category}' does not represent a business service enquiry."
    return points, reason


# Dimension 2: Requirement clarity
def _score_requirement_clarity(requirement: str | None) -> tuple[int, str]:
    if not requirement:
        return 0, "No specific requirement identified from the enquiry."

    length = len(requirement.strip())

    if length >= 100:
        return 20, "Requirement is detailed and clearly defined."
    elif length >= 60:
        return 15, "Requirement is moderately clear with sufficient detail."
    elif length >= 30:
        return 10, "Requirement is present but somewhat vague."
    elif length >= 10:
        return 5, "Requirement is very brief and lacks specificity."
    else:
        return 2, "Requirement field is too short to assess clearly."


# Dimension 3: Budget information
BUDGET_NUMBER_PATTERN = re.compile(r"[\d,]+")


def _score_budget(budget: str | None) -> tuple[int, str]:
    if not budget:
        return 0, "No budget information provided."

    budget_lower = budget.lower().strip()

    if BUDGET_NUMBER_PATTERN.search(budget):
        return 15, f"Specific budget mentioned: '{budget}'."

    vague_keywords = ["flexible", "open", "negotiable", "budget available", "have budget"]
    if any(kw in budget_lower for kw in vague_keywords):
        return 8, "Budget mentioned but not quantified."

    return 5, "Budget reference present but unclear."


# Dimension 4: Timeline and urgency
URGENCY_KEYWORDS = {
    "immediately", "asap", "urgent", "this week", "today", "right away",
    "as soon as possible", "start immediately", "want to start",
}


def _score_timeline(expected_timeline: str | None) -> tuple[int, str]:
    if not expected_timeline:
        return 0, "No timeline or urgency information provided."

    timeline_lower = expected_timeline.lower()

    if any(kw in timeline_lower for kw in URGENCY_KEYWORDS):
        return 15, f"Urgent timeline stated: '{expected_timeline}'."

    if any(kw in timeline_lower for kw in ["week", "days", "month"]):
        return 10, f"Near-term timeline mentioned: '{expected_timeline}'."

    return 6, f"Timeline mentioned but not urgent: '{expected_timeline}'."


# Dimension 5: Project scope
SCALE_PATTERN = re.compile(r"\d+\s*(users?|enquir|customer|order|product|day|month|per)", re.IGNORECASE)
SYSTEM_KEYWORDS = {
    "erp", "crm", "api", "integration", "automation", "system", "platform",
    "dashboard", "inventory", "dispatch", "whatsapp", "chatbot", "document",
}


def _score_project_scope(requirement: str | None, category: str) -> tuple[int, str]:
    if not requirement:
        return 0, "Project scope cannot be assessed without a clear requirement."

    req_lower = requirement.lower()
    score = 0
    notes = []

    if len(requirement) >= 80:
        score += 10
        notes.append("detailed requirement description")
    elif len(requirement) >= 40:
        score += 6
        notes.append("moderate requirement detail")
    else:
        score += 2
        notes.append("brief requirement")

    if SCALE_PATTERN.search(requirement):
        score += 6
        notes.append("quantified scale mentioned")

    matched_systems = [kw for kw in SYSTEM_KEYWORDS if kw in req_lower]
    if len(matched_systems) >= 2:
        score += 4
        notes.append(f"multiple technical systems referenced ({', '.join(matched_systems[:3])})")
    elif len(matched_systems) == 1:
        score += 2
        notes.append(f"technical system referenced ({matched_systems[0]})")

    score = min(score, 20)
    reason = f"Project scope: {'; '.join(notes)}." if notes else "Limited scope information."
    return score, reason


def _assign_priority(score: int) -> str:
    if score >= 70:
        return "High"
    elif score >= 40:
        return "Medium"
    return "Low"


def calculate_lead_score(extracted: ExtractedInfo) -> LeadScore:
    """Calculate lead score (0-100) and priority based on 5 dimensions."""
    reasons: list[str] = []

    rel_points, rel_reason = _score_business_relevance(extracted.category or "Other")
    req_points, req_reason = _score_requirement_clarity(extracted.requirement)
    bud_points, bud_reason = _score_budget(extracted.budget)
    tim_points, tim_reason = _score_timeline(extracted.expected_timeline)
    sco_points, sco_reason = _score_project_scope(extracted.requirement, extracted.category or "Other")

    total = rel_points + req_points + bud_points + tim_points + sco_points
    total = min(total, 100)

    reasons = [rel_reason, req_reason, bud_reason, tim_reason, sco_reason]
    priority = _assign_priority(total)

    logger.info(
        "Lead score: %d | priority: %s | category: %s | "
        "relevance=%d req=%d budget=%d timeline=%d scope=%d",
        total, priority, extracted.category,
        rel_points, req_points, bud_points, tim_points, sco_points,
    )

    return LeadScore(score=total, priority=priority, reasons=reasons)

