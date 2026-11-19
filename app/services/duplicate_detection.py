"""Duplicate enquiry detection using text normalization and similarity matching."""

from datetime import datetime, timedelta, timezone
import difflib
import logging
import re
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from config import get_settings
from models import Enquiry
from schemas import DuplicateCheckResult

logger = logging.getLogger(__name__)


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Strip whitespace and lowercase email."""
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned if cleaned else None


def normalize_text(text: str) -> str:
    """Normalize text for reliable similarity comparison."""
    if not text:
        return ""
    # Lowercase
    cleaned = text.lower()
    # Replace punctuation and special characters with spaces
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Collapse multiple whitespaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity ratio (0.0 to 1.0) using SequenceMatcher.
    Uses normalized strings for comparison.
    """
    n1 = normalize_text(text1)
    n2 = normalize_text(text2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def check_duplicate_enquiry(
    email: Optional[str],
    message: str,
    db: Session,
    window_days: Optional[int] = None,
    threshold: Optional[float] = None,
    exclude_enquiry_id: Optional[int] = None,
) -> DuplicateCheckResult:
    """
    Checks if an enquiry is a potential duplicate within the lookback window.

    Rules:
    1. If email is provided:
       - Query previous enquiries from the same email within `window_days`.
       - If message matches exactly (or normalized text matches 100%), flag as duplicate.
       - If similarity ratio >= `threshold`, flag as near-duplicate.
       - If similarity < threshold, it is considered an UNRELATED enquiry from the same customer (not duplicate).
    2. If no email is provided:
       - Query recent enquiries across all sources within `window_days`.
       - Check for exact or highly similar messages (similarity >= threshold).
    """
    settings = get_settings()
    days = window_days if window_days is not None else settings.duplicate_detection_window_days
    sim_threshold = threshold if threshold is not None else settings.duplicate_similarity_threshold

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    norm_email = normalize_email(email)
    norm_msg = normalize_text(message)

    query = db.query(Enquiry).filter(Enquiry.created_at >= cutoff_date)

    if exclude_enquiry_id:
        query = query.filter(Enquiry.id != exclude_enquiry_id)

    if norm_email:
        # Check against enquiries with the same normalized email
        candidates = query.filter(Enquiry.email.ilike(norm_email)).order_by(Enquiry.created_at.desc()).all()
    else:
        # When no email, only check against recent enquiries with message content
        candidates = query.order_by(Enquiry.created_at.desc()).limit(50).all()

    for candidate in candidates:
        cand_norm_msg = normalize_text(candidate.message)

        # 1. Exact match
        if norm_msg == cand_norm_msg:
            delta = datetime.now(timezone.utc) - (candidate.created_at.replace(tzinfo=timezone.utc) if candidate.created_at.tzinfo is None else candidate.created_at)
            days_ago = max(0, delta.days)
            time_desc = "today" if days_ago == 0 else (f"1 day ago" if days_ago == 1 else f"{days_ago} days ago")
            
            return DuplicateCheckResult(
                is_duplicate=True,
                original_enquiry_id=candidate.id,
                original_created_at=candidate.created_at,
                similarity_score=1.0,
                message=f"Exact duplicate detected. This customer submitted identical enquiry {time_desc} (Enquiry #EQ-{candidate.id:03d}).",
            )

        # 2. Near-duplicate similarity check
        sim_score = calculate_text_similarity(message, candidate.message)
        if sim_score >= sim_threshold:
            delta = datetime.now(timezone.utc) - (candidate.created_at.replace(tzinfo=timezone.utc) if candidate.created_at.tzinfo is None else candidate.created_at)
            days_ago = max(0, delta.days)
            time_desc = "today" if days_ago == 0 else (f"1 day ago" if days_ago == 1 else f"{days_ago} days ago")
            
            pct = int(sim_score * 100)
            return DuplicateCheckResult(
                is_duplicate=True,
                original_enquiry_id=candidate.id,
                original_created_at=candidate.created_at,
                similarity_score=round(sim_score, 3),
                message=f"Potential duplicate detected ({pct}% match). Customer submitted a similar enquiry {time_desc} (Enquiry #EQ-{candidate.id:03d}).",
            )

    return DuplicateCheckResult(is_duplicate=False)
