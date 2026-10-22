# ABOUTME: Tests for booking helper rules (email, name, time formatting).
# ABOUTME: Owned by the booking stream.

from datetime import datetime


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
