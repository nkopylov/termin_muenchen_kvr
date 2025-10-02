"""
Database initialization and session management
Provides connection pooling and session lifecycle management
"""
from sqlmodel import SQLModel, create_engine, Session
from contextlib import contextmanager
from typing import Generator
import logging

from config import get_config
from db_models import User, ServiceSubscription, AppointmentLog

logger = logging.getLogger(__name__)

# Global engine instance
_engine = None


def get_engine():
    """Get or create the global database engine"""
    global _engine
    if _engine is None:
        config = get_config()
        database_url = f"sqlite:///{config.db_file}"

        _engine = create_engine(
            database_url,
            echo=False,  # Set to True for SQL debugging
            connect_args={"check_same_thread": False}  # Needed for SQLite
        )

        logger.info(f"Database engine created: {config.db_file}")

    return _engine


def init_database() -> None:
    """
    Initialize database tables
    Creates all tables if they don't exist
    """
    engine = get_engine()

    # Create all tables
    SQLModel.metadata.create_all(engine)

    logger.info("Database tables initialized")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get a database session with automatic commit/rollback

    Usage:
        with get_session() as session:
            user = session.get(User, user_id)
            ...

    Yields:
        Session: SQLModel session
    """
    engine = get_engine()
    session = Session(engine)

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_database() -> None:
    """Close database connections"""
    global _engine
    if _engine:
        _engine.dispose()
        _engine = None
        logger.info("Database connections closed")
