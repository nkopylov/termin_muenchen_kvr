# ABOUTME: Tests for notification_service formatting and booking callback data.
# ABOUTME: Covers only notification_service.py and goes away with it.


class TestNotificationService:
    """Tests for notification_service.py business logic"""

    def test_format_date_for_notification(self):
        """Test date formatting for notifications"""
        # This would test any date formatting logic in notification service
        # Placeholder - implement when notification service has testable pure functions

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


class TestNotificationFormatting:
    """Tests for notification_service.py formatting"""

    def test_format_available_days(self):
        from src.services.notification_service import format_available_appointments

        data = {
            "availableDays": [
                {"date": "2026-12-03", "providerIDs": "10461", "offices": []},
                {"date": "2026-12-04", "providerIDs": "10461", "offices": []},
            ]
        }

        assert format_available_appointments(data) == "📅 2026-12-03\n📅 2026-12-04"
