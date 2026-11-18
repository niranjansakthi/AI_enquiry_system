"""
main.py
───────
FastAPI application entry point.

Responsibilities:
- Create the FastAPI app instance
- Register all routers
- Mount the static files directory
- Configure Jinja2 templates
- Create database tables on startup
- Configure application-wide logging
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import get_settings
from database import create_tables

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Curd Rice Business Studio – Enquiry Automation",
    description="AI-powered business enquiry processing system",
    version="1.0.0",
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    """Create database tables and log that the application has started."""
    create_tables()
    logger.info("Database tables verified / created.")
    logger.info("Application started in '%s' mode.", settings.app_env)


# ─────────────────────────────────────────────────────────────────────────────
# Routers – imported after app is defined to avoid circular imports
# ─────────────────────────────────────────────────────────────────────────────
from app.routers import enquiries, drafts, dashboard  # noqa: E402

app.include_router(enquiries.router, prefix="/api", tags=["enquiries"])
app.include_router(drafts.router, prefix="/api", tags=["drafts"])
app.include_router(dashboard.router, tags=["dashboard"])

