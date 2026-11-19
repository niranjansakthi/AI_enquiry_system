"""
app/services/response_validator.py
Deterministic safety and business policy validator for AI-generated response drafts.

Validates email drafts against Curd Rice Business Studio policy rules before
marking them ready for human review. Does not call an LLM; all checks are
deterministic pattern and keyword evaluations.
"""

import logging
import re
from typing import Optional

from schemas import ExtractedInfo, SafetyValidationResult, ValidationIssue

logger = logging.getLogger(__name__)

# Currency & pricing patterns
PRICING_PATTERNS = [
    r"(\$|€|£|₹|rs\.?|inr|usd)\s*\d+([,\.]\d+)?",
    r"\d+\s*(dollars|euros|pounds|rupees|inr|usd|lakhs?|crores?)\b",
    r"\b(cost is|priced at|quote is|package starts at|our fee is)\s*[:\$₹\d]",
]

# Guarantee & unverified promises
GUARANTEE_PATTERNS = [
    r"\b(we guarantee|100% guarantee|guaranteed results|guaranteed delivery|guaranteed roi)\b",
    r"\b(promise to deliver|guarantee that your|guarantee of success)\b",
    r"\b(we promise you|contractually guaranteed)\b",
]

# Strict deadline/timeline commitment patterns
TIMELINE_COMMITMENT_PATTERNS = [
    r"\b(will deliver by|ready within \d+\s*(hours|days)|deliver in \d+\s*days|guarantee completion by)\b",
    r"\b(project will be completed by|ready by tomorrow|definitely launched within)\b",
]

# Unauthorized commitment patterns
UNAUTHORIZED_COMMITMENTS = [
    r"\b(we agree to work for free|no charge at all|waive all fees|service has been confirmed|project has been approved)\b",
    r"\b(contract is finalized|deal is locked)\b",
]


def validate_response_draft(
    subject: str,
    body: str,
    category: str,
    extracted: Optional[ExtractedInfo] = None,
) -> SafetyValidationResult:
    """
    Perform deterministic validation on an AI-generated email draft.

    Returns SafetyValidationResult detailing any safety violations,
    policy warnings, or mandatory human review escalations.
    """
    issues: list[ValidationIssue] = []
    combined_text = f"{subject}\n{body}".lower()

    # 1. Pricing and quotes check
    for pattern in PRICING_PATTERNS:
        matches = re.findall(pattern, combined_text, re.IGNORECASE)
        if matches:
            issues.append(
                ValidationIssue(
                    code="UNAUTHORIZED_PRICING",
                    severity="HIGH",
                    description="Response contains explicit pricing or monetary quotes contrary to company policy.",
                )
            )
            break

    # 2. Guarantees and unverified results check
    for pattern in GUARANTEE_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            issues.append(
                ValidationIssue(
                    code="UNSUPPORTED_GUARANTEE",
                    severity="HIGH",
                    description="Response makes unverified guarantees or performance promises.",
                )
            )
            break

    # 3. Firm delivery date/timeline commitment check
    for pattern in TIMELINE_COMMITMENT_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            issues.append(
                ValidationIssue(
                    code="UNAUTHORIZED_TIMELINE_COMMITMENT",
                    severity="HIGH",
                    description="Response commits to a specific delivery date or turnaround time without human approval.",
                )
            )
            break

    # 4. Unauthorized business commitments check
    for pattern in UNAUTHORIZED_COMMITMENTS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            issues.append(
                ValidationIssue(
                    code="UNAUTHORIZED_COMMITMENT",
                    severity="HIGH",
                    description="Response implies a finalized contract, free work, or pre-approved service.",
                )
            )
            break

    # 5. Salutation and greeting check
    body_stripped = body.strip().lower()
    has_greeting = any(
        body_stripped.startswith(g)
        for g in ["dear ", "hello ", "hi ", "greetings", "good morning", "good afternoon"]
    )
    if not has_greeting:
        issues.append(
            ValidationIssue(
                code="MISSING_GREETING",
                severity="LOW",
                description="Draft lacks a formal greeting or salutation.",
            )
        )

    # 6. Sign-off check
    has_signoff = any(
        s in body_stripped
        for s in ["regards", "warmly", "curd rice", "team", "sincerely", "best regards"]
    )
    if not has_signoff:
        issues.append(
            ValidationIssue(
                code="MISSING_SIGNOFF",
                severity="LOW",
                description="Draft lacks a company sign-off from Curd Rice Business Studio.",
            )
        )

    # 7. Complaint category validation
    if category == "Complaint":
        # Complaints must have empathetic tone and should not brush off the issue
        dismissive_words = ["not our fault", "cannot help you", "nothing we can do", "you should have"]
        if any(w in combined_text for w in dismissive_words):
            issues.append(
                ValidationIssue(
                    code="INAPPROPRIATE_COMPLAINT_TONE",
                    severity="HIGH",
                    description="Draft contains dismissive language in response to a customer complaint.",
                )
            )
        if not any(w in combined_text for w in ["apolog", "sorry", "escalat", "investigat", "resolve"]):
            issues.append(
                ValidationIssue(
                    code="COMPLAINT_MISSING_ACKNOWLEDGEMENT",
                    severity="MEDIUM",
                    description="Complaint response does not clearly acknowledge the issue or mention escalation.",
                )
            )

    # 8. Next steps check for business enquiries
    if category in {"AI Automation", "Application Development", "Website Development", "Business Consulting"}:
        next_step_keywords = ["call", "meeting", "discuss", "connect", "schedule", "questions", "share", "details"]
        if not any(w in combined_text for w in next_step_keywords):
            issues.append(
                ValidationIssue(
                    code="MISSING_NEXT_STEPS",
                    severity="MEDIUM",
                    description="Commercial enquiry response lacks a clear call-to-action or next step.",
                )
            )

    # Determine status & human review requirement
    has_high = any(issue.severity == "HIGH" for issue in issues)
    has_medium = any(issue.severity == "MEDIUM" for issue in issues)

    if has_high:
        status = "FAILED"
        is_safe = False
        requires_human_review = True
        explanation = f"Safety validator blocked automatic draft approval due to {len(issues)} policy violation(s)."
    elif has_medium:
        status = "WARNING"
        is_safe = True
        requires_human_review = True
        explanation = "Response contains warnings that should be reviewed by a human operator."
    elif issues:
        status = "PASSED_WITH_NOTICES"
        is_safe = True
        requires_human_review = False
        explanation = "Response meets safety criteria with minor stylistic notices."
    else:
        status = "PASSED"
        is_safe = True
        requires_human_review = False
        explanation = "Draft passed all deterministic safety and business policy checks."

    logger.info(
        "Response validation status: %s (safe=%s, issues=%d, requires_review=%s)",
        status, is_safe, len(issues), requires_human_review,
    )

    return SafetyValidationResult(
        is_safe=is_safe,
        status=status,
        issues=issues,
        requires_human_review=requires_human_review,
        explanation=explanation,
    )
