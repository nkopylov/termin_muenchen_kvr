"""
Pytest configuration and shared fixtures for tests
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    """Create in-memory SQLite database engine for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Keep single connection for in-memory DB
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="db_session")
def db_session_fixture(db_engine):
    """Create database session for testing"""
    with Session(db_engine) as session:
        yield session
        session.rollback()  # Rollback any uncommitted changes after test
