"""Database configuration and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import get_settings


def _build_engine():
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(settings.database_url, pool_pre_ping=True)


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency providing a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Initialize database tables and handle schema migrations."""
    import models  # registers ORM models
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

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
