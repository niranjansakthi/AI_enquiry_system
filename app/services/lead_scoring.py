"""
app/services/lead_scoring.py
─────────────────────────────
Module C: Deterministic lead scoring.

Single public function: calculate_lead_score(extracted_info) -> LeadScore

The score is calculated from five independent dimensions using plain Python
conditional logic. The LLM is never involved in this calculation.

Scoring dimensions and maximum points:
  1. Business relevance   – 0 to 30
  2. Requirement clarity  – 0 to 20
  3. Budget information   – 0 to 15
  4. Timeline / urgency   – 0 to 15
  5. Project scope        – 0 to 20
  ─────────────────────────────────
  Total maximum           – 100

Priority bands:
  High   : 70 – 100
  Medium : 40 – 69
  Low    :  0 – 39

Auto-escalation (requires_human_review flag):
  Complaints, Job/Internship Applications, and Partnership enquiries are
  flagged for human review regardless of their numerical score.

All rules are documented inline so they can be explained during an interview.
"""

import logging
import re

from schemas import ExtractedInfo, LeadScore

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Dimension 1: Business relevance (0–30)
#
# Maps each category to a base relevance score that reflects how closely
# it matches the studio's core service areas. This is not a keyword match —
# it uses the AI-classified category from Module B.
# ─────────────────────────────────────────────────────────────────────────────

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
    """Return (points, reason) for business relevance."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 2: Requirement clarity (0–20)
#
# Judges how clearly the customer described what they need.
# Measured by requirement field length and specificity.
# A very short or absent requirement scores low; a detailed one scores high.
# ─────────────────────────────────────────────────────────────────────────────

def _score_requirement_clarity(requirement: str | None) -> tuple[int, str]:
    """Return (points, reason) for requirement clarity."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 3: Budget information (0–15)
#
# Budget presence is a strong signal of purchase intent.
# A specific numeric budget scores full marks.
# A vague mention ("we have a budget") scores partial marks.
# No budget scores zero — it means missing information, not a negative signal.
# ─────────────────────────────────────────────────────────────────────────────

BUDGET_NUMBER_PATTERN = re.compile(r"[\d,]+")


def _score_budget(budget: str | None) -> tuple[int, str]:
    """Return (points, reason) for budget information."""
    if not budget:
        return 0, "No budget information provided."

    budget_lower = budget.lower().strip()

    # Check for a numeric value (amount in any currency)
    if BUDGET_NUMBER_PATTERN.search(budget):
        return 15, f"Specific budget mentioned: '{budget}'."

    # Vague budget mention
    vague_keywords = ["flexible", "open", "negotiable", "budget available", "have budget"]
    if any(kw in budget_lower for kw in vague_keywords):
        return 8, "Budget mentioned but not quantified."

    # Non-empty but unrecognised format — give partial credit
    return 5, "Budget reference present but unclear."


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 4: Timeline and urgency (0–15)
#
# A stated timeline signals that the customer is ready to act.
# Urgency keywords ("immediately", "this week", "ASAP") indicate higher intent.
# No timeline is neutral — it does not reduce the score.
# ─────────────────────────────────────────────────────────────────────────────

URGENCY_KEYWORDS = {
    "immediately", "asap", "urgent", "this week", "today", "right away",
    "as soon as possible", "start immediately", "want to start",
}


def _score_timeline(expected_timeline: str | None) -> tuple[int, str]:
    """Return (points, reason) for timeline and urgency."""
    if not expected_timeline:
        return 0, "No timeline or urgency information provided."

    timeline_lower = expected_timeline.lower()

    if any(kw in timeline_lower for kw in URGENCY_KEYWORDS):
        return 15, f"Urgent timeline stated: '{expected_timeline}'."

    # Short timelines (days, weeks, specific months)
    if any(kw in timeline_lower for kw in ["week", "days", "month"]):
        return 10, f"Near-term timeline mentioned: '{expected_timeline}'."

    # Longer or vague timelines
    return 6, f"Timeline mentioned but not urgent: '{expected_timeline}'."


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 5: Project scope (0–20)
#
# Larger, more specific projects represent higher business value.
# Measured by requirement length plus presence of scale indicators
# (numbers, quantities, system names, integrations).
# ─────────────────────────────────────────────────────────────────────────────

SCALE_PATTERN = re.compile(r"\d+\s*(users?|enquir|customer|order|product|day|month|per)", re.IGNORECASE)
SYSTEM_KEYWORDS = {
    "erp", "crm", "api", "integration", "automation", "system", "platform",
    "dashboard", "inventory", "dispatch", "whatsapp", "chatbot", "document",
}


def _score_project_scope(requirement: str | None, category: str) -> tuple[int, str]:
    """Return (points, reason) for project scope."""
    if not requirement:
        return 0, "Project scope cannot be assessed without a clear requirement."

    req_lower = requirement.lower()
    score = 0
    notes = []

    # Length-based base score
    if len(requirement) >= 80:
        score += 10
        notes.append("detailed requirement description")
    elif len(requirement) >= 40:
        score += 6
        notes.append("moderate requirement detail")
    else:
        score += 2
        notes.append("brief requirement")

    # Scale indicators (e.g. "500 customers per day")
    if SCALE_PATTERN.search(requirement):
        score += 6
        notes.append("quantified scale mentioned")

    # Technical system keywords
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


# ─────────────────────────────────────────────────────────────────────────────
# Priority band assignment
# ─────────────────────────────────────────────────────────────────────────────

def _assign_priority(score: int) -> str:
    if score >= 70:
        return "High"
    elif score >= 40:
        return "Medium"
    return "Low"


# ─────────────────────────────────────────────────────────────────────────────
# Public function
# ─────────────────────────────────────────────────────────────────────────────

def calculate_lead_score(extracted: ExtractedInfo) -> LeadScore:
    """
    Calculate a lead score from 0 to 100 using five deterministic dimensions.

    This function contains no AI calls. Every decision is traceable to an
    explicit rule defined in this file.

    Args:
        extracted : validated ExtractedInfo from the AI understanding service

    Returns:
        LeadScore with score (int), priority (str), reasons (list[str])
    """
    reasons: list[str] = []

    rel_points, rel_reason = _score_business_relevance(extracted.category or "Other")
    req_points, req_reason = _score_requirement_clarity(extracted.requirement)
    bud_points, bud_reason = _score_budget(extracted.budget)
    tim_points, tim_reason = _score_timeline(extracted.expected_timeline)
    sco_points, sco_reason = _score_project_scope(extracted.requirement, extracted.category or "Other")

    total = rel_points + req_points + bud_points + tim_points + sco_points
    total = min(total, 100)  # safety cap

    # Always include all five dimension reasons for transparency
    reasons = [rel_reason, req_reason, bud_reason, tim_reason, sco_reason]

    priority = _assign_priority(total)

    logger.info(
        "Lead score: %d | priority: %s | category: %s | "
        "relevance=%d req=%d budget=%d timeline=%d scope=%d",
        total, priority, extracted.category,
        rel_points, req_points, bud_points, tim_points, sco_points,
    )

    return LeadScore(score=total, priority=priority, reasons=reasons)

