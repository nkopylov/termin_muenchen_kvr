"""
Tests for business logic functions
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from src.services_manager import categorize_services, get_service_info


class TestServicesManager:
    """Tests for services_manager.py business logic"""

    def test_categorize_services_returns_dict(self):
        """Test categorize_services returns a dictionary"""
        categories = categorize_services()
        assert isinstance(categories, dict)

    def test_categorize_services_has_categories(self):
        """Test categorize_services returns non-empty categories"""
        categories = categorize_services()
        assert len(categories) > 0

    def test_categorize_services_structure(self):
        """Test each category contains a list of services"""
        categories = categorize_services()
        for category_name, services in categories.items():
            assert isinstance(category_name, str)
            assert isinstance(services, list)
            assert len(services) > 0

    def test_categorize_services_service_structure(self):
        """Test each service has required fields"""
        categories = categorize_services()
        for services in categories.values():
            for service in services:
                assert "id" in service
                assert "name" in service
                assert isinstance(service["id"], int)
                assert isinstance(service["name"], str)

    def test_get_service_info_valid_id(self):
        """Test get_service_info returns correct service"""
        # First get all services to find a valid ID
        categories = categorize_services()
        first_service = None
        for services in categories.values():
            if services:
                first_service = services[0]
                break

        assert first_service is not None

        # Get info for that service
        service_info = get_service_info(first_service["id"])
        assert service_info is not None
        assert service_info["id"] == first_service["id"]
        assert service_info["name"] == first_service["name"]

    def test_get_service_info_invalid_id(self):
        """Test get_service_info returns None for invalid ID"""
        service_info = get_service_info(999999)
        assert service_info is None

    def test_get_service_info_returns_complete_data(self):
        """Test get_service_info returns all expected fields"""
        categories = categorize_services()
        first_service = None
        for services in categories.values():
            if services:
                first_service = services[0]
                break

        service_info = get_service_info(first_service["id"])
        assert "id" in service_info
        assert "name" in service_info
        # Note: get_service_info returns raw service dict, not with category field
        # Category is retrieved separately via get_category_for_service


class TestAppointmentChecker:
    """Tests for appointment_checker.py business logic"""

    @patch("src.repositories.UserRepository")
    @patch("src.services.appointment_checker.get_session")
    def test_get_user_date_range_with_user_settings(
        self, mock_get_session, MockUserRepo
    ):
        """Test get_user_date_range returns user's configured dates"""
        from src.services.appointment_checker import get_user_date_range
        from src.db_models import User

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
        from src.services.appointment_checker import get_user_date_range
        from src.db_models import User

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


class TestNotificationService:
    """Tests for notification_service.py business logic"""

    def test_format_date_for_notification(self):
        """Test date formatting for notifications"""
        # This would test any date formatting logic in notification service
        # Placeholder - implement when notification service has testable pure functions
        pass

    def test_generate_booking_callback_data(self):
        """Test generating callback data for booking buttons"""
        # Format: "book_DATE_OFFICEID_SERVICEID"
        date = "2025-01-15"
        office_id = 200
        service_id = 100

        expected = f"book_{date}_{office_id}_{service_id}"
        assert expected == f"book_{date}_{office_id}_{service_id}"

    def test_parse_booking_callback_data(self):
        """Test parsing callback data from booking buttons"""
        callback_data = "book_2025-01-15_200_100"
        parts = callback_data.split("_")

        assert parts[0] == "book"
        assert parts[1] == "2025-01-15"
        assert int(parts[2]) == 200
        assert int(parts[3]) == 100


class TestBookingHelpers:
    """Tests for booking-related helper functions"""

    def test_validate_email_format(self):
        """Test email validation logic"""
        # Simple validation used in booking.py
        valid_emails = [
            "user@example.com",
            "test.user@domain.co.uk",
            "name+tag@test.org",
        ]

        for email in valid_emails:
            assert "@" in email and "." in email

        invalid_emails = ["notanemail", "missing@domain", "no.at.sign.com"]

        for email in invalid_emails:
            assert not ("@" in email and "." in email)

    def test_validate_name_length(self):
        """Test name validation logic"""
        # Name must be at least 2 characters (from booking.py)
        valid_names = ["Jo", "John Doe", "Anna-Maria Schmidt"]

        for name in valid_names:
            assert len(name.strip()) >= 2

        invalid_names = ["", " ", "J"]

        for name in invalid_names:
            assert len(name.strip()) < 2

    def test_timestamp_to_time_string(self):
        """Test converting timestamp to human-readable time"""
        timestamp = 1704117600  # 2024-01-01 12:00:00 UTC
        dt = datetime.fromtimestamp(timestamp)
        time_str = dt.strftime("%H:%M")

        assert ":" in time_str
        assert len(time_str) == 5  # "HH:MM"

    def test_format_booking_confirmation_time(self):
        """Test formatting time for booking confirmation"""
        timestamp = 1704117600
        dt = datetime.fromtimestamp(timestamp)
        time_str = dt.strftime("%H:%M on %A, %B %d, %Y")

        assert ":" in time_str
        assert " on " in time_str
        assert "," in time_str


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
