"""
conftest.py
───────────
Pytest configuration and shared test fixtures.
Uses an in-memory SQLite database so unit/integration tests run fast, isolated,
and never affect the real database or consume Groq API tokens.
"""

import sys
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure root path is accessible
sys.path.insert(0, ".")

from database import Base, get_db
from main import app
from schemas import ExtractedInfo, DraftContent

# Test database setup (SQLite in-memory with StaticPool for cross-thread sharing)
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_extracted_info() -> ExtractedInfo:
    return ExtractedInfo(
        category="AI Automation",
        customer_name="Ramesh",
        company_name="Jewellery Corp",
        email="ramesh@example.com",
        requirement="AI-powered WhatsApp customer support system",
        budget="50,000",
        expected_timeline="immediately",
        intent="Automate customer support",
        confidence=0.95,
        requires_human_review=False,
        review_reason=None,
    )

