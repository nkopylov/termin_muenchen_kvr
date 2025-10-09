"""
Queue manager for tracking users in active booking conversations.
Prevents appointment notifications from interrupting booking flows.
"""
import time
import logging

logger = logging.getLogger(__name__)

# Track users currently in booking conversation (to pause notifications)
active_booking_users = {}  # {user_id: timestamp}

BOOKING_TIMEOUT = 600  # 10 minutes


def add_user_to_queue(user_id: int) -> None:
    """Mark user as in booking mode (notifications paused)"""
    active_booking_users[user_id] = time.time()
    logger.info(f"User {user_id} entered booking mode - notifications paused")


def remove_user_from_queue(user_id: int) -> None:
    """Remove user from booking mode (notifications resumed)"""
    if user_id in active_booking_users:
        del active_booking_users[user_id]
        logger.info(f"User {user_id} exited booking mode - notifications resumed")


def is_user_in_queue(user_id: int) -> bool:
    """Check if user is currently in booking mode"""
    if user_id not in active_booking_users:
        return False

    # Check if booking session is stale (>10 minutes)
    booking_start_time = active_booking_users[user_id]
    if time.time() - booking_start_time > BOOKING_TIMEOUT:
        logger.info(f"Booking session for user {user_id} timed out, removing from active list")
        del active_booking_users[user_id]
        return False

    return True


def cleanup_stale_sessions() -> int:
    """Remove stale booking sessions that exceeded timeout. Returns number of sessions cleaned."""
    stale_users = []
    current_time = time.time()

    for user_id, start_time in active_booking_users.items():
        if current_time - start_time > BOOKING_TIMEOUT:
            stale_users.append(user_id)

    for user_id in stale_users:
        del active_booking_users[user_id]
        logger.info(f"Cleaned up stale booking session for user {user_id}")

    return len(stale_users)
