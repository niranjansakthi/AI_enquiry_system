"""Application entry point and routing setup."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import get_settings
from database import create_tables

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    logger.info("Database initialized.")
    logger.info("App running in '%s' mode.", settings.app_env)
    yield


app = FastAPI(
    title="Curd Rice Business Studio – Enquiry Automation",
    description="Business enquiry automation and response platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Routers
from app.routers import enquiries, drafts, dashboard  # noqa: E402

app.include_router(enquiries.router, prefix="/api", tags=["enquiries"])
app.include_router(drafts.router, prefix="/api", tags=["drafts"])
app.include_router(dashboard.router, tags=["dashboard"])

