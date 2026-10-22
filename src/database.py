"""
Database initialization and session management
Provides connection pooling and session lifecycle management
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from itertools import groupby

from sqlmodel import Session, SQLModel, create_engine

import src.db_models  # noqa: F401  (registers tables on SQLModel.metadata)
from src.config import get_config
from src.watches import when

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
            connect_args={"check_same_thread": False},  # Needed for SQLite
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
    _run_migrations(engine)

    logger.info("Database tables initialized")


def _run_migrations(engine) -> None:
    """Apply one-time data migrations, tracked with SQLite's PRAGMA user_version"""
    with engine.begin() as conn:
        version = conn.exec_driver_sql("PRAGMA user_version").scalar()
        if version < 1:
            # Existing users are asked to choose their language on next interaction
            conn.exec_driver_sql("UPDATE users SET language = ''")
            conn.exec_driver_sql("PRAGMA user_version = 1")
            logger.info("Migration 1 applied: user languages reset to unset")
            version = 1
        if version < 2:
            _add_column_if_missing(conn, "users", "booking_name", "VARCHAR(255)")
            _add_column_if_missing(conn, "users", "booking_email", "VARCHAR(255)")
            _add_column_if_missing(conn, "users", "nav_message_id", "INTEGER")
            _add_column_if_missing(
                conn, "users", "ui_version", "INTEGER NOT NULL DEFAULT 0"
            )
            _add_column_if_missing(conn, "booking_sessions", "watch_id", "INTEGER")
            _add_column_if_missing(conn, "booking_sessions", "message_id", "INTEGER")
            created = _migrate_subscriptions_to_watches(
                conn, when.today_berlin(), when.utcnow()
            )
            conn.exec_driver_sql("PRAGMA user_version = 2")
            logger.info(f"Migration 2 applied: {created} watch(es) from subscriptions")


def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _db_datetime(value: datetime) -> str:
    # Same text format SQLAlchemy uses for SQLite DATETIME columns
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _migrate_subscriptions_to_watches(conn, today: date, now: datetime) -> int:
    """One open watch per (user, service) from service_subscriptions; returns watches created"""
    rows = conn.exec_driver_sql(
        "SELECT s.user_id, s.service_id, s.office_id, u.start_date, u.end_date "
        "FROM service_subscriptions s JOIN users u USING (user_id) ORDER BY 1, 2, 3"
    ).all()
    created = 0
    for (user_id, service_id), group in groupby(rows, key=lambda r: (r[0], r[1])):
        group = list(group)
        offices = {r[2] for r in group if r[2] is not None}
        office_id = offices.pop() if len(offices) == 1 else None
        spec = when.migrated_when(group[0][3], group[0][4], today)

        open_watch = conn.exec_driver_sql(
            "SELECT 1 FROM watches WHERE user_id = ? AND service_id = ? "
            "AND status IN ('active', 'paused')",
            (user_id, service_id),
        ).first()
        if open_watch is not None:
            continue

        stamp = _db_datetime(now)
        conn.exec_driver_sql(
            "INSERT INTO watches (user_id, service_id, office_id, when_kind, within_days, "
            "date_from, date_to, status, created_at, updated_at, alerted_slots, "
            "alert_shown_slots) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, '[]', '[]')",
            (
                user_id,
                service_id,
                office_id,
                spec.kind,
                spec.within_days,
                _iso(spec.date_from),
                _iso(spec.date_to),
                stamp,
                stamp,
            ),
        )
        created += 1
    return created


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
