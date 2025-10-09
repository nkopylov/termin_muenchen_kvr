"""
Queue manager for tracking users in active booking conversations.
Prevents appointment notifications from interrupting booking flows.
Uses DB-backed session storage for persistence across bot restarts.
"""

import logging
from src.database import get_session
from src.repositories import BookingSessionRepository

logger = logging.getLogger(__name__)


def is_user_in_queue(user_id: int) -> bool:
    """
    Check if user is currently in booking mode.
    Uses DB-backed session storage - survives bot restarts.
    """
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        return booking_repo.is_user_in_booking(user_id)


def get_active_user_count() -> int:
    """Get count of users currently in booking mode"""
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        return len(booking_repo.get_all_active_sessions())


def cleanup_stale_sessions() -> int:
    """Remove stale booking sessions that exceeded timeout. Returns number of sessions cleaned."""
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        count = booking_repo.cleanup_expired_sessions()
        if count > 0:
            logger.info(f"Cleaned up {count} expired booking session(s)")
        return count
