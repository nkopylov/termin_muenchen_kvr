# ABOUTME: Tests for the queue manager and the checker's stats counters.
# ABOUTME: Owned by the checker stream; real in-memory DB, fixed clock.

from datetime import timedelta

import pytest
from sqlmodel import Session

from src.repositories import BookingSessionRepository
from src.services import appointment_checker
from src.services.queue_manager import is_user_in_queue
from tests.conftest import NOW

USER = 12345


def start_booking(db, expires_at):
    with Session(db) as session:
        BookingSessionRepository(session).create_session(
            USER, "SELECTING_TIME", 1063475, 0, "2026-10-29", "", expires_at
        )


def session_row(db):
    with Session(db) as session:
        return BookingSessionRepository(session).get_session(USER)


@pytest.mark.usefixtures("clock")
class TestQueueManager:
    def test_user_with_unexpired_booking_is_in_queue(self, db):
        start_booking(db, NOW + timedelta(seconds=1))
        assert is_user_in_queue(USER) is True

    def test_user_without_booking_is_not_in_queue(self, db):
        assert is_user_in_queue(USER) is False

    def test_expired_booking_is_not_in_queue_and_is_left_for_cleanup(self, db):
        start_booking(db, NOW)
        assert is_user_in_queue(USER) is False
        assert session_row(db) is not None


class TestStatsTracking:
    """Tests for statistics tracking logic"""

    def test_stats_structure(self):
        """Test stats dictionary has expected structure"""
        from src.services.appointment_checker import get_stats

        stats = get_stats()

        expected_keys = [
            "total_checks",
            "successful_checks",
            "failed_checks",
            "appointments_found_count",
            "last_check_time",
            "last_success_time",
            "bot_start_time",
        ]

        for key in expected_keys:
            assert key in stats

    def test_booking_counters(self, monkeypatch):
        monkeypatch.setitem(appointment_checker.stats, "bookings_started", 0)
        monkeypatch.setitem(appointment_checker.stats, "bookings_completed", 0)

        appointment_checker.increment_bookings_started()
        appointment_checker.increment_bookings_started()
        appointment_checker.increment_bookings_completed()

        stats = appointment_checker.get_stats()
        assert (stats["bookings_started"], stats["bookings_completed"]) == (2, 1)

    def test_set_bot_start_time(self, monkeypatch):
        monkeypatch.setitem(appointment_checker.stats, "bot_start_time", None)
        appointment_checker.set_bot_start_time()
        assert appointment_checker.get_stats()["bot_start_time"] is not None
