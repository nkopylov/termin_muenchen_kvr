"""
Queue manager for tracking users in active booking conversations.
Prevents appointment notifications from interrupting booking flows.
Uses DB-backed session storage for persistence across bot restarts.
"""

from src.database import get_session
from src.repositories import BookingSessionRepository


def is_user_in_queue(user_id: int) -> bool:
    """
    Check if user is currently in booking mode.
    Uses DB-backed session storage - survives bot restarts.
    """
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        return booking_repo.is_user_in_booking(user_id)
