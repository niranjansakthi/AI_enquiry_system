"""Enquiry understanding and entity extraction using Groq LLM."""

import json
import logging
import time
from typing import Optional

from groq import Groq, APITimeoutError, APIConnectionError, APIStatusError

from config import BUSINESS_CONTEXT, ENQUIRY_CATEGORIES, get_settings
from schemas import ExtractedInfo

logger = logging.getLogger(__name__)


class AIExtractionError(Exception):
    """Raised when extraction fails after all retries."""
    pass


# Prompt configuration
SYSTEM_PROMPT = f"""You are an intelligent business enquiry analyst for Curd Rice Business Studio.

{BUSINESS_CONTEXT}

Your task is to analyse a customer enquiry and extract structured information from it.

Extract the following fields:
- category: classify into exactly one of these categories:
  {', '.join(ENQUIRY_CATEGORIES)}
- customer_name: the person's name if mentioned, else null
- company_name: the business or company name if mentioned, else null
- email: email address if mentioned, else null
- requirement: a clear one-to-two sentence summary of what the customer needs
- budget: the budget if mentioned (keep original currency and amount), else null
- expected_timeline: when they want to start or complete (e.g. "this week", "3 months"), else null
- intent: a short phrase describing the customer's business intent
- confidence: your confidence in the classification as a decimal between 0.0 and 1.0
- requires_human_review: true if the enquiry is a complaint, legally sensitive,
  contains threats, is too ambiguous to classify, or requires urgent human attention
- review_reason: brief reason if requires_human_review is true, else null

Rules:
- Never invent information. Use null for anything not stated in the enquiry.
- Do not guess budget or timeline if not mentioned.
- Keep requirement factual and concise.
- Respond ONLY with valid JSON matching the schema below. No explanation, no markdown.

Required JSON schema:
{{
  "category": "string",
  "customer_name": "string or null",
  "company_name": "string or null",
  "email": "string or null",
  "requirement": "string or null",
  "budget": "string or null",
  "expected_timeline": "string or null",
  "intent": "string or null",
  "confidence": 0.0,
  "requires_human_review": false,
  "review_reason": "string or null"
}}"""


def _build_user_message(message: str, existing_name: Optional[str], existing_email: Optional[str]) -> str:
    """
    Build the user-turn message for the extraction prompt.
    Pre-fill known fields so the model doesn't need to guess them.
    """
    context_lines = []
    if existing_name:
        context_lines.append(f"Submitted by: {existing_name}")
    if existing_email:
        context_lines.append(f"Email on file: {existing_email}")

    context = "\n".join(context_lines)
    if context:
        return f"{context}\n\nEnquiry message:\n{message}"
    return f"Enquiry message:\n{message}"


# ─────────────────────────────────────────────────────────────────────────────
# JSON parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    """
    Extract the JSON object from the model's response.

    The model is instructed to return only JSON, but it sometimes wraps
    the output in markdown code fences. This strips those fences before
    parsing.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (```json or ```)
        lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIExtractionError(f"Model returned invalid JSON: {exc}\nRaw response: {raw[:300]}")


# ─────────────────────────────────────────────────────────────────────────────
# Public function
# ─────────────────────────────────────────────────────────────────────────────

def extract_enquiry_info(
    message: str,
    existing_name: Optional[str] = None,
    existing_email: Optional[str] = None,
) -> ExtractedInfo:
    """
    Send an enquiry message to Groq and return structured ExtractedInfo.

    Retries up to settings.groq_max_retries times on transient failures.
    Raises AIExtractionError if all attempts fail.

    Args:
        message       : the raw enquiry text
        existing_name : customer name already known from the submission form
        existing_email: email already known from the submission form

    Returns:
        ExtractedInfo – validated Pydantic model
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    user_message = _build_user_message(message, existing_name, existing_email)

    last_error: Optional[Exception] = None
    attempts = settings.groq_max_retries + 1  # e.g. max_retries=2 → 3 total attempts

    for attempt in range(1, attempts + 1):
        try:
            logger.debug("AI extraction attempt %d/%d", attempt, attempts)

            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,   # low temperature for consistent structured output
                max_tokens=600,
                timeout=settings.groq_timeout,
            )

            raw = response.choices[0].message.content
            if not raw:
                raise AIExtractionError("Model returned an empty response.")

            data = _parse_json_response(raw)

            # Merge pre-known fields: if the model left them null but we have
            # them from the form submission, fill them in.
            if existing_name and not data.get("customer_name"):
                data["customer_name"] = existing_name
            if existing_email and not data.get("email"):
                data["email"] = existing_email

            extracted = ExtractedInfo(**data)
            logger.info(
                "Extraction successful: category=%s confidence=%.2f",
                extracted.category,
                extracted.confidence,
            )
            return extracted

        except (APITimeoutError, APIConnectionError) as exc:
            last_error = exc
            logger.warning("Groq API transient error on attempt %d: %s", attempt, exc)
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))  # 1s, 2s back-off

        except AIExtractionError:
            raise  # JSON / parse errors are not retried

        except APIStatusError as exc:
            # 4xx errors are not retried (bad key, quota, etc.)
            raise AIExtractionError(f"Groq API error {exc.status_code}: {exc.message}") from exc

        except Exception as exc:
            last_error = exc
            logger.warning("Unexpected error on attempt %d: %s", attempt, exc)
            if attempt < attempts:
                time.sleep(1)

    raise AIExtractionError(
        f"AI extraction failed after {attempts} attempts. Last error: {last_error}"
    )

