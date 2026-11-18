"""
database.py
───────────
Creates the SQLAlchemy engine and session factory.

get_db() is a FastAPI dependency that opens a session for a request and
closes it cleanly when the request finishes, whether it succeeded or failed.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import get_settings


def _build_engine():
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        # SQLite requires this to allow use across FastAPI's threadpool workers.
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
        )
    # PostgreSQL and other databases work without extra connect_args.
    # pool_pre_ping=True verifies connections before use — avoids stale
    # connection errors after the server restarts or idles out.
    return create_engine(settings.database_url, pool_pre_ping=True)


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def get_db():
    """
    FastAPI dependency.

    Yields a database session and guarantees it is closed after the
    request finishes, even if an exception is raised.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """
    Create all tables that do not yet exist. Called once at startup.

    Models must be imported before this runs so SQLAlchemy's metadata
    registry knows about them. The import is done here to keep all
    table-creation logic in one place.
    """
    import models  # noqa: F401 — registers Enquiry, EnquiryAnalysis, ResponseDraft
    Base.metadata.create_all(bind=engine)
