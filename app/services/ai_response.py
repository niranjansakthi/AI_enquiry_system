"""Contextual email response draft generator using Groq LLM."""

import json
import logging
import time
from typing import Optional

from groq import Groq, APITimeoutError, APIConnectionError, APIStatusError

from config import BUSINESS_CONTEXT, get_settings
from schemas import DraftContent, ExtractedInfo, LeadScore

logger = logging.getLogger(__name__)


class AIResponseError(Exception):
    """Raised when draft generation fails after all retries."""
    pass


# Tone guidance
TONE_BUSINESS = """
Write a professional, warm and helpful reply to a business service enquiry.
- Address the customer's specific requirement directly.
- Express genuine interest in understanding more about their needs.
- Ask one or two relevant clarifying questions if important details are missing.
- Do not list all services generically; focus on what is relevant to this enquiry.
- For pricing enquiries: politely explain that pricing is discussed after understanding
  the actual requirements, and invite them to schedule a conversation.
"""

TONE_COMPLAINT = """
Write an empathetic, professional and urgent response to a complaint.
- Acknowledge the customer's experience sincerely.
- Apologise for any inconvenience caused (without admitting liability).
- Confirm that the matter will be escalated to the appropriate team member.
- Do not make promises about resolution outcomes or timelines.
- Keep the tone calm, respectful and solution-oriented.
"""

TONE_INTERNSHIP = """
Write a professional and encouraging response to an internship or job application enquiry.
- Thank the applicant for their interest.
- Explain that the team will review applications and reach out if there is a match.
- Do not make any promises about positions, roles or joining dates.
- Keep the tone friendly but appropriately professional.
"""

TONE_PARTNERSHIP = """
Write a professional and open-minded response to a partnership enquiry.
- Acknowledge the interest in collaboration.
- Express willingness to understand more about the opportunity.
- Ask for more details about the nature of the proposed partnership.
- Do not make any commitment on behalf of the company.
"""


def _select_tone(category: str) -> str:
    """Return the appropriate tone instruction based on enquiry category."""
    if category == "Complaint":
        return TONE_COMPLAINT
    if category == "Job and Internship Application":
        return TONE_INTERNSHIP
    if category == "Partnership":
        return TONE_PARTNERSHIP
    return TONE_BUSINESS


# System prompt builder
def _build_system_prompt(category: str) -> str:
    tone = _select_tone(category)
    return f"""You are drafting a professional email response on behalf of Curd Rice Business Studio.

{BUSINESS_CONTEXT}

Tone and style guidance:
{tone}

Absolute restrictions — never violate these:
- Do not invent or quote specific service prices or packages.
- Do not guarantee any project delivery dates or timelines.
- Do not make commitments on behalf of the company.
- Do not claim that any service has been confirmed or approved.
- Do not fabricate company achievements, case studies, or client references.
- Do not use generic promotional language or buzzwords.

Output format — respond ONLY with valid JSON in this exact shape:
{{
  "subject": "Re: [relevant subject line here]",
  "body": "Full email body text here. Use \\n for line breaks."
}}

The email body should:
- Begin with a greeting using the customer's name if available.
- Be concise — 3 to 5 short paragraphs.
- End with a professional sign-off from the Curd Rice Business Studio team.
- Not include any placeholders like [NAME] or [DATE].
"""


def _build_user_message(
    extracted: ExtractedInfo,
    lead_score: LeadScore,
    enquiry_message: str,
) -> str:
    """Build the context block passed as the user message."""
    parts = [f"Original enquiry:\n{enquiry_message}"]

    if extracted.customer_name:
        parts.append(f"Customer name: {extracted.customer_name}")
    if extracted.company_name:
        parts.append(f"Company: {extracted.company_name}")
    if extracted.requirement:
        parts.append(f"Identified requirement: {extracted.requirement}")
    if extracted.budget:
        parts.append(f"Budget mentioned: {extracted.budget}")
    if extracted.expected_timeline:
        parts.append(f"Timeline mentioned: {extracted.expected_timeline}")
    if extracted.intent:
        parts.append(f"Customer intent: {extracted.intent}")

    parts.append(f"Category: {extracted.category}")
    parts.append(f"Lead priority: {lead_score.priority} (score {lead_score.score}/100)")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# JSON parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_draft_response(raw: str) -> DraftContent:
    """
    Parse the JSON response from the model into a DraftContent object.
    Handles markdown code fences the same way as ai_understanding.py.
    """
    text = raw.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"Model returned invalid JSON: {exc}\nRaw: {raw[:300]}")

    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()

    if not subject or not body:
        raise AIResponseError("Model response missing 'subject' or 'body' field.")

    return DraftContent(subject=subject, body=body)


# ─────────────────────────────────────────────────────────────────────────────
# Public function
# ─────────────────────────────────────────────────────────────────────────────

def generate_email_draft(
    enquiry_message: str,
    extracted: ExtractedInfo,
    lead_score: LeadScore,
) -> DraftContent:
    """
    Generate a personalised email draft for the given enquiry.

    Uses extracted information and lead score to build the prompt.
    Retries on transient Groq errors up to settings.groq_max_retries times.

    Args:
        enquiry_message : the original raw enquiry text
        extracted       : validated ExtractedInfo from Module B
        lead_score      : LeadScore from Module C

    Returns:
        DraftContent with subject and body strings
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    system_prompt = _build_system_prompt(extracted.category or "General Enquiry")
    user_message = _build_user_message(extracted, lead_score, enquiry_message)

    last_error: Optional[Exception] = None
    attempts = settings.groq_max_retries + 1

    for attempt in range(1, attempts + 1):
        try:
            logger.debug("Draft generation attempt %d/%d", attempt, attempts)

            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.4,   # slightly more creative than extraction
                max_tokens=800,
                timeout=settings.groq_timeout,
            )

            raw = response.choices[0].message.content
            if not raw:
                raise AIResponseError("Model returned an empty response.")

            draft = _parse_draft_response(raw)
            logger.info("Email draft generated for category: %s", extracted.category)
            return draft

        except (APITimeoutError, APIConnectionError) as exc:
            last_error = exc
            logger.warning("Groq transient error on attempt %d: %s", attempt, exc)
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))

        except AIResponseError:
            raise

        except APIStatusError as exc:
            raise AIResponseError(f"Groq API error {exc.status_code}: {exc.message}") from exc

        except Exception as exc:
            last_error = exc
            logger.warning("Unexpected error on attempt %d: %s", attempt, exc)
            if attempt < attempts:
                time.sleep(1)

    raise AIResponseError(
        f"Draft generation failed after {attempts} attempts. Last error: {last_error}"
    )

