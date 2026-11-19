"""Validation and string sanitization helpers."""

import re
from typing import Optional


def is_valid_email(email: str) -> bool:
    """
    Quick email format check.
    Pydantic's EmailStr does the full validation for API inputs.
    This helper is used when processing CSV rows where Pydantic
    isn't directly applied to individual cells.
    """
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def clean_optional_str(value: Optional[str]) -> Optional[str]:
    """
    Strip whitespace from a string field.
    Returns None if the result is empty.
    Used when mapping CSV columns to EnquiryCreate fields.
    """
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def sanitise_message(message: str) -> str:
    """
    Strip leading/trailing whitespace and normalise internal whitespace.
    Does not alter the content of the message.
    """
    # Collapse multiple consecutive blank lines into one
    lines = message.strip().splitlines()
    cleaned = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 1:
                cleaned.append(line)
        else:
            blank_count = 0
            cleaned.append(line)
    return "\n".join(cleaned)

