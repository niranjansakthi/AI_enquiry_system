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
    Also ensures missing columns are added if running against an existing database.
    """
    import models  # noqa: F401 — registers Enquiry, EnquiryAnalysis, ResponseDraft
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

    # Auto-migration for newly added columns on existing databases
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.connect() as conn:
        if "enquiries" in existing_tables:
            cols = {c["name"] for c in inspector.get_columns("enquiries")}
            if "is_duplicate" not in cols:
                conn.execute(text("ALTER TABLE enquiries ADD COLUMN is_duplicate BOOLEAN NOT NULL DEFAULT FALSE"))
            if "duplicate_of_id" not in cols:
                conn.execute(text("ALTER TABLE enquiries ADD COLUMN duplicate_of_id INTEGER"))
            if "duplicate_reason" not in cols:
                conn.execute(text("ALTER TABLE enquiries ADD COLUMN duplicate_reason TEXT"))

        if "enquiry_analysis" in existing_tables:
            cols = {c["name"] for c in inspector.get_columns("enquiry_analysis")}
            if "qualification_missing_info" not in cols:
                conn.execute(text("ALTER TABLE enquiry_analysis ADD COLUMN qualification_missing_info TEXT"))
            if "clarification_questions" not in cols:
                conn.execute(text("ALTER TABLE enquiry_analysis ADD COLUMN clarification_questions TEXT"))

        if "response_drafts" in existing_tables:
            cols = {c["name"] for c in inspector.get_columns("response_drafts")}
            if "validation_status" not in cols:
                conn.execute(text("ALTER TABLE response_drafts ADD COLUMN validation_status VARCHAR(30) NOT NULL DEFAULT 'PASSED'"))
            if "validation_issues" not in cols:
                conn.execute(text("ALTER TABLE response_drafts ADD COLUMN validation_issues TEXT"))

        conn.commit()
