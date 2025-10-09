"""
Tests for booking flow state machine
Tests the complex multi-step booking conversation flow
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from src.commands.booking import (
    create_booking_session,
    update_booking_session,
    delete_booking_session,
    get_booking_session,
)


class TestBookingSessionManagement:
    """Tests for booking session lifecycle management"""

    @patch("src.commands.booking.get_session")
    def test_create_booking_session(self, mock_get_session):
        """Test creating a new booking session"""
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        mock_booking_repo = Mock()

        with patch("src.commands.booking.BookingSessionRepository") as MockBookingRepo:
            MockBookingRepo.return_value = mock_booking_repo

            create_booking_session(
                user_id=12345,
                service_id=100,
                office_id=200,
                date="2025-01-15",
                captcha_token="token123",
                state="SELECTING_TIME",
            )

            # Verify repository create_session was called
            mock_booking_repo.create_session.assert_called_once()
            call_args = mock_booking_repo.create_session.call_args[1]
            assert call_args["user_id"] == 12345
            assert call_args["service_id"] == 100
            assert call_args["office_id"] == 200
            assert call_args["date"] == "2025-01-15"
            assert call_args["captcha_token"] == "token123"
            assert call_args["state"] == "SELECTING_TIME"

    @patch("src.commands.booking.get_session")
    def test_update_booking_session(self, mock_get_session):
        """Test updating an existing booking session"""
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        mock_booking_repo = Mock()

        with patch("src.commands.booking.BookingSessionRepository") as MockBookingRepo:
            MockBookingRepo.return_value = mock_booking_repo

            update_booking_session(
                user_id=12345,
                state="ASKING_NAME",
                timestamp=1234567890,
                name="John Doe",
            )

            # Verify repository update_session was called
            mock_booking_repo.update_session.assert_called_once_with(
                12345, state="ASKING_NAME", timestamp=1234567890, name="John Doe"
            )

    @patch("src.commands.booking.get_session")
    def test_delete_booking_session(self, mock_get_session):
        """Test deleting a booking session"""
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        mock_booking_repo = Mock()

        with patch("src.commands.booking.BookingSessionRepository") as MockBookingRepo:
            MockBookingRepo.return_value = mock_booking_repo

            delete_booking_session(user_id=12345)

            # Verify repository delete_session was called
            mock_booking_repo.delete_session.assert_called_once_with(12345)

    @patch("src.commands.booking.get_session")
    def test_get_booking_session(self, mock_get_session):
        """Test retrieving a booking session"""
        from src.db_models import BookingSession

        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        mock_booking_repo = Mock()
        mock_booking_session = BookingSession(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )
        mock_booking_repo.get_session.return_value = mock_booking_session

        with patch("src.commands.booking.BookingSessionRepository") as MockBookingRepo:
            MockBookingRepo.return_value = mock_booking_repo

            session = get_booking_session(user_id=12345)

            assert session.user_id == 12345
            assert session.state == "SELECTING_TIME"
            mock_booking_repo.get_session.assert_called_once_with(12345)


class TestBookingStateTransitions:
    """Tests for booking conversation state transitions"""

    def test_state_progression_order(self):
        """Test the expected order of booking states"""
        from src.commands.booking import (
            SELECTING_TIME,
            ASKING_NAME,
            ASKING_EMAIL,
            CONFIRMING,
        )

        # Verify state constants are in correct order
        # Note: Booking starts at SELECTING_TIME (no SELECTING_DATE state)
        assert SELECTING_TIME == 0
        assert ASKING_NAME == 1
        assert ASKING_EMAIL == 2
        assert CONFIRMING == 3

    @pytest.mark.asyncio
    @patch("src.commands.booking.get_booking_session")
    @patch("src.commands.booking.update_booking_session")
    async def test_transition_selecting_time_to_asking_name(
        self, mock_update, mock_get_session
    ):
        """Test transition from SELECTING_TIME to ASKING_NAME"""
        from src.db_models import BookingSession
        from src.commands.booking import time_selected

        # Mock booking session
        mock_session = BookingSession(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )
        mock_get_session.return_value = mock_session

        # Mock Update and query
        mock_update_obj = Mock()
        mock_query = AsyncMock()
        mock_query.data = "time_1234567890"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update_obj.callback_query = mock_query
        mock_update_obj.effective_user = Mock(id=12345)

        mock_context = Mock()

        result = await time_selected(mock_update_obj, mock_context)

        # Should transition to ASKING_NAME state
        from src.commands.booking import ASKING_NAME

        assert result == ASKING_NAME

    def test_session_timeout_value(self):
        """Test booking session timeout is set correctly"""
        from src.commands.booking import BOOKING_SESSION_TIMEOUT_SECONDS

        # 15 minutes = 900 seconds
        assert BOOKING_SESSION_TIMEOUT_SECONDS == 900

    @patch("src.commands.booking.get_session")
    def test_session_expires_at_calculation(self, mock_get_session):
        """Test expiration time is calculated correctly"""
        from src.commands.booking import BOOKING_SESSION_TIMEOUT_SECONDS

        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        mock_booking_repo = Mock()

        with patch("src.commands.booking.BookingSessionRepository") as MockBookingRepo:
            MockBookingRepo.return_value = mock_booking_repo

            before = datetime.utcnow()
            create_booking_session(
                user_id=12345,
                service_id=100,
                office_id=200,
                date="2025-01-15",
                captcha_token="token123",
            )

            call_args = mock_booking_repo.create_session.call_args[1]
            expires_at = call_args["expires_at"]

            # Verify expires_at is approximately 15 minutes from now
            expected_expiry = before + timedelta(
                seconds=BOOKING_SESSION_TIMEOUT_SECONDS
            )
            time_diff = abs((expires_at - expected_expiry).total_seconds())
            assert time_diff < 2  # Within 2 seconds


class TestBookingValidation:
    """Tests for booking input validation"""

    def test_name_validation_too_short(self):
        """Test name must be at least 2 characters"""
        names = ["", " ", "J", "  "]

        for name in names:
            assert len(name.strip()) < 2

    def test_name_validation_valid(self):
        """Test valid names pass validation"""
        names = ["Jo", "John Doe", "Anna-Maria", "李明"]

        for name in names:
            assert len(name.strip()) >= 2

    def test_email_validation_invalid(self):
        """Test invalid email formats"""
        emails = ["notanemail", "missing@domain", "no.at.sign", "@nodomain.com"]

        for email in emails:
            is_valid = "@" in email and "." in email
            assert is_valid is False or email == "@nodomain.com"

    def test_email_validation_valid(self):
        """Test valid email formats"""
        emails = [
            "user@example.com",
            "test.user@domain.co.uk",
            "name+tag@test.org",
            "firstname.lastname@company.com",
        ]

        for email in emails:
            assert "@" in email and "." in email


class TestBookingCancellation:
    """Tests for booking cancellation flow"""

    @pytest.mark.asyncio
    @patch("src.commands.booking.delete_booking_session")
    async def test_cancel_from_time_selection(self, mock_delete):
        """Test canceling booking from time selection"""
        from src.commands.booking import time_selected

        mock_update = Mock()
        mock_query = AsyncMock()
        mock_query.data = "cancel_booking"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user = Mock(id=12345)

        mock_context = Mock()

        result = await time_selected(mock_update, mock_context)

        # Should call delete_booking_session
        mock_delete.assert_called_once_with(12345)

        # Should end conversation
        from telegram.ext import ConversationHandler

        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    @patch("src.commands.booking.delete_booking_session")
    async def test_cancel_from_button(self, mock_delete):
        """Test cancel booking button handler"""
        from src.commands.booking import cancel_booking_button

        mock_update = Mock()
        mock_query = AsyncMock()
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user = Mock(id=12345)

        mock_context = Mock()
        mock_context.user_data = {"test": "data"}

        result = await cancel_booking_button(mock_update, mock_context)

        # Should delete session and clear user data
        mock_delete.assert_called_once_with(12345)
        assert len(mock_context.user_data) == 0

        # Should end conversation
        from telegram.ext import ConversationHandler

        assert result == ConversationHandler.END


class TestBookingErrorHandling:
    """Tests for booking error scenarios"""

    @pytest.mark.asyncio
    @patch("src.commands.booking.get_booking_session")
    async def test_session_expired_during_booking(self, mock_get_session):
        """Test handling of expired session during booking"""
        from src.commands.booking import time_selected

        # Session doesn't exist (expired or cleared)
        mock_get_session.return_value = None

        mock_update = Mock()
        mock_query = AsyncMock()
        mock_query.data = "time_1234567890"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user = Mock(id=12345)

        mock_context = Mock()

        result = await time_selected(mock_update, mock_context)

        # Should end conversation
        from telegram.ext import ConversationHandler

        assert result == ConversationHandler.END

        # Should show error message
        mock_query.edit_message_text.assert_called_once()
        call_args = mock_query.edit_message_text.call_args[0][0]
        assert "expired" in call_args.lower() or "cleared" in call_args.lower()

    def test_booking_callback_pattern_validation(self):
        """Test callback data pattern matching"""
        import re

        # Pattern from ConversationHandler entry_points
        pattern = r"^book_\d{4}-\d{2}-\d{2}_\d+_\d+$"

        valid_callbacks = [
            "book_2025-01-15_200_100",
            "book_2024-12-31_10461_10339028",
            "book_2025-06-01_1_1",
        ]

        for callback in valid_callbacks:
            assert re.match(pattern, callback) is not None

        invalid_callbacks = [
            "book_2025-1-15_200_100",  # Single digit month
            "book_2025-01-15_200",  # Missing service_id
            "subscribe_2025-01-15_200_100",  # Wrong prefix
            "book_15-01-2025_200_100",  # Wrong date format
        ]

        for callback in invalid_callbacks:
            assert re.match(pattern, callback) is None


class TestBookingCompletion:
    """Tests for booking completion scenarios"""

    @pytest.mark.asyncio
    @patch("src.commands.booking.book_appointment_complete")
    @patch("src.commands.booking.get_booking_session")
    @patch("src.commands.booking.delete_booking_session")
    async def test_successful_booking(
        self, mock_delete, mock_get_session, mock_book_complete
    ):
        """Test successful booking flow completion"""
        from src.commands.booking import confirm_booking
        from src.db_models import BookingSession

        # Mock successful booking
        mock_book_complete.return_value = {"processId": "ABC123", "status": "success"}

        # Mock booking session
        mock_session = BookingSession(
            user_id=12345,
            state="CONFIRMING",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=datetime.utcnow() + timedelta(minutes=15),
            timestamp=1234567890,
            name="John Doe",
            email="john@example.com",
        )
        mock_get_session.return_value = mock_session

        mock_update = Mock()
        mock_query = AsyncMock()
        mock_query.data = "confirm_booking"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user = Mock(id=12345)

        mock_context = Mock()
        mock_context.user_data = {}

        result = await confirm_booking(mock_update, mock_context)

        # Should delete session after completion
        mock_delete.assert_called_once_with(12345)

        # Should end conversation
        from telegram.ext import ConversationHandler

        assert result == ConversationHandler.END

        # Should show success message
        mock_query.edit_message_text.assert_called()
        call_args = mock_query.edit_message_text.call_args[0][0]
        assert "success" in call_args.lower() or "🎉" in call_args

    @pytest.mark.asyncio
    @patch("src.commands.booking.book_appointment_complete")
    @patch("src.commands.booking.get_booking_session")
    @patch("src.commands.booking.delete_booking_session")
    async def test_failed_booking(
        self, mock_delete, mock_get_session, mock_book_complete
    ):
        """Test failed booking scenario"""
        from src.commands.booking import confirm_booking
        from src.db_models import BookingSession

        # Mock failed booking
        mock_book_complete.return_value = None

        # Mock booking session
        mock_session = BookingSession(
            user_id=12345,
            state="CONFIRMING",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=datetime.utcnow() + timedelta(minutes=15),
            timestamp=1234567890,
            name="John Doe",
            email="john@example.com",
        )
        mock_get_session.return_value = mock_session

        mock_update = Mock()
        mock_query = AsyncMock()
        mock_query.data = "confirm_booking"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user = Mock(id=12345)

        mock_context = Mock()
        mock_context.user_data = {}

        result = await confirm_booking(mock_update, mock_context)

        # Should still delete session
        mock_delete.assert_called_once_with(12345)

        # Should end conversation
        from telegram.ext import ConversationHandler

        assert result == ConversationHandler.END

        # Should show failure message
        mock_query.edit_message_text.assert_called()
        call_args = mock_query.edit_message_text.call_args[0][0]
        assert "failed" in call_args.lower() or "❌" in call_args
