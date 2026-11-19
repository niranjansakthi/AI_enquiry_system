"""
config.py
─────────
Loads all environment variables and exposes a single Settings object.
Also holds the BUSINESS_CONTEXT constant that is passed into AI prompts.

No secrets are hardcoded here. Every sensitive value must be present in .env.
"""

import logging
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Groq AI
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout: int = 30
    groq_max_retries: int = 2

    # Database
    database_url: str = "sqlite:///./enquiries.db"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    duplicate_detection_window_days: int = 7
    duplicate_similarity_threshold: float = 0.85

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings. Fails fast if required vars are missing."""
    try:
        return Settings()
    except Exception as exc:
        logging.critical("Failed to load settings: %s", exc)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Business context injected into AI prompts.
# Keep this concise and factually accurate. Do not exaggerate services.
# ─────────────────────────────────────────────────────────────────────────────
BUSINESS_CONTEXT = """
Business name: Curd Rice Business Studio

Focus areas:
- Business Intelligence and reporting
- Operational systems (ERP, inventory, dispatch management)
- AI Automation (chatbots, document processing, customer support automation)
- Website and application development
- Branding and digital marketing support

About:
Curd Rice Business Studio helps businesses improve their operations, make
better decisions and implement technology-driven solutions. The studio works
primarily with small and medium businesses across manufacturing, retail and
service sectors.

Important restrictions for AI-generated responses:
- Never invent service pricing or quote specific costs.
- Never guarantee project delivery dates or timelines.
- Never make commitments on behalf of the company.
- Never claim that a service has been confirmed or approved.
- Never generate misleading or fabricated information.
- Do not provide fabricated company achievements or case studies.
- Escalate unclear, sensitive or complaint-type enquiries to a human reviewer.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Supported enquiry categories. Shared by schemas and AI prompts.
# ─────────────────────────────────────────────────────────────────────────────
ENQUIRY_CATEGORIES = [
    "Business Consulting",
    "AI Automation",
    "Website Development",
    "Application Development",
    "Branding and Marketing",
    "General Enquiry",
    "Job and Internship Application",
    "Partnership",
    "Complaint",
    "Other",
]

# Categories that always require human review regardless of lead score.
ESCALATION_CATEGORIES = {"Complaint", "Partnership", "Job and Internship Application"}

