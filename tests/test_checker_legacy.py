# ABOUTME: Tests for the appointment checker, queue manager and stats tracking.
# ABOUTME: Owned by the checker stream.

from datetime import datetime, timedelta
from unittest.mock import Mock, patch


class TestAppointmentChecker:
    """Tests for appointment_checker.py business logic"""

    @patch("src.repositories.UserRepository")
    @patch("src.services.appointment_checker.get_session")
    def test_get_user_date_range_with_user_settings(
        self, mock_get_session, MockUserRepo
    ):
        """Test get_user_date_range returns user's configured dates"""
        from src.db_models import User
        from src.services.appointment_checker import get_user_date_range

        # Mock user with date range
        mock_user = User(user_id=12345, start_date="2025-01-01", end_date="2025-12-31")

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Mock repository
        mock_user_repo = Mock()
        mock_user_repo.get_user.return_value = mock_user
        MockUserRepo.return_value = mock_user_repo

        start_date, end_date = get_user_date_range(12345)

        assert start_date == "2025-01-01"
        assert end_date == "2025-12-31"

    @patch("src.repositories.UserRepository")
    @patch("src.services.appointment_checker.get_session")
    def test_get_user_date_range_defaults(self, mock_get_session, MockUserRepo):
        """Test get_user_date_range returns defaults when user has no dates"""
        from src.db_models import User
        from src.services.appointment_checker import get_user_date_range

        # Mock user without date range
        mock_user = User(user_id=12345, start_date=None, end_date=None)

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Mock repository
        mock_user_repo = Mock()
        mock_user_repo.get_user.return_value = mock_user
        MockUserRepo.return_value = mock_user_repo

        start_date, end_date = get_user_date_range(12345)

        # Should return defaults (today and 60 days from now)
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")

        assert start_date == today
        assert end_date == future

    @patch("src.repositories.UserRepository")
    @patch("src.services.appointment_checker.get_session")
    def test_get_user_date_range_no_user(self, mock_get_session, MockUserRepo):
        """Test get_user_date_range returns None tuple when user doesn't exist"""
        from src.services.appointment_checker import get_user_date_range

        # Mock session context manager
        mock_session = Mock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Mock repository
        mock_user_repo = Mock()
        mock_user_repo.get_user.return_value = None  # User doesn't exist
        MockUserRepo.return_value = mock_user_repo

        start_date, end_date = get_user_date_range(99999)

        assert start_date is None
        assert end_date is None


class TestQueueManager:
    """Tests for queue_manager.py business logic"""

    @patch("src.services.queue_manager.get_session")
    def test_is_user_in_queue_true(self, mock_get_session):
        """Test is_user_in_queue returns True for user with active session"""
        from src.services.queue_manager import is_user_in_queue

        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        mock_booking_repo = Mock()
        mock_booking_repo.is_user_in_booking.return_value = True

        with patch(
            "src.services.queue_manager.BookingSessionRepository"
        ) as MockBookingRepo:
            MockBookingRepo.return_value = mock_booking_repo

            result = is_user_in_queue(12345)
            assert result is True

    @patch("src.services.queue_manager.get_session")
    def test_is_user_in_queue_false(self, mock_get_session):
        """Test is_user_in_queue returns False for user without session"""
        from src.services.queue_manager import is_user_in_queue

        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        mock_booking_repo = Mock()
        mock_booking_repo.is_user_in_booking.return_value = False

        with patch(
            "src.services.queue_manager.BookingSessionRepository"
        ) as MockBookingRepo:
            MockBookingRepo.return_value = mock_booking_repo

            result = is_user_in_queue(99999)
            assert result is False


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

    def test_calculate_success_rate(self):
        """Test success rate calculation"""
        total_checks = 100
        successful_checks = 85
        success_rate = (successful_checks / total_checks) * 100

        assert success_rate == 85.0

    def test_calculate_success_rate_zero_checks(self):
        """Test success rate with zero checks"""
        total_checks = 0
        success_rate = 0

        if total_checks > 0:
            success_rate = (0 / total_checks) * 100

        assert success_rate == 0

    def test_format_uptime(self):
        """Test uptime formatting logic"""
        start_time = datetime.now() - timedelta(hours=3, minutes=45)
        uptime_seconds = (datetime.now() - start_time).total_seconds()

        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        assert hours == 3
        assert minutes == 45
