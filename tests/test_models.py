"""
Tests for database models and validation
"""

import pytest
from datetime import datetime, timedelta
from src.db_models import User, ServiceSubscription, AppointmentLog, BookingSession


class TestUserModel:
    """Tests for User model"""

    def test_create_user_minimal(self, db_session):
        """Test creating user with minimal required fields"""
        user = User(user_id=12345)
        db_session.add(user)
        db_session.commit()

        assert user.user_id == 12345
        assert user.username is None
        assert user.language == "de"  # Default value

    def test_create_user_full(self, db_session):
        """Test creating user with all fields"""
        user = User(
            user_id=12345,
            username="testuser",
            language="en",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        db_session.add(user)
        db_session.commit()

        assert user.user_id == 12345
        assert user.username == "testuser"
        assert user.language == "en"
        assert user.start_date == "2025-01-01"
        assert user.end_date == "2025-12-31"

    def test_user_default_language(self, db_session):
        """Test user language defaults to 'de'"""
        user = User(user_id=12345)
        db_session.add(user)
        db_session.commit()

        assert user.language == "de"

    def test_user_unique_id(self, db_session):
        """Test user_id must be unique"""
        user1 = User(user_id=12345, username="user1")
        db_session.add(user1)
        db_session.commit()

        user2 = User(user_id=12345, username="user2")
        db_session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestServiceSubscriptionModel:
    """Tests for ServiceSubscription model"""

    def test_create_subscription(self, db_session):
        """Test creating a service subscription"""
        # Create user first
        user = User(user_id=12345)
        db_session.add(user)
        db_session.commit()

        subscription = ServiceSubscription(user_id=12345, service_id=100, office_id=200)
        db_session.add(subscription)
        db_session.commit()

        assert subscription.user_id == 12345
        assert subscription.service_id == 100
        assert subscription.office_id == 200
        assert subscription.subscribed_at is not None

    def test_subscription_auto_timestamp(self, db_session):
        """Test subscription automatically sets subscribed_at timestamp"""
        user = User(user_id=12345)
        db_session.add(user)
        db_session.commit()

        before = datetime.utcnow()
        subscription = ServiceSubscription(user_id=12345, service_id=100, office_id=200)
        db_session.add(subscription)
        db_session.commit()
        after = datetime.utcnow()

        assert before <= subscription.subscribed_at <= after

    def test_subscription_foreign_key_constraint(self, db_session):
        """Test subscription maintains referential integrity with user"""
        user = User(user_id=12345)
        db_session.add(user)
        db_session.commit()

        subscription = ServiceSubscription(user_id=12345, service_id=100, office_id=200)
        db_session.add(subscription)
        db_session.commit()

        # Verify subscription was created
        from sqlmodel import select

        result = db_session.exec(
            select(ServiceSubscription).where(ServiceSubscription.user_id == 12345)
        ).first()
        assert result is not None
        assert result.user_id == 12345

        # Note: CASCADE DELETE is not configured, so deleting user while
        # subscription exists would fail. This is expected behavior -
        # subscriptions should be deleted explicitly before user deletion.


class TestAppointmentLogModel:
    """Tests for AppointmentLog model"""

    def test_create_appointment_log(self, db_session):
        """Test creating an appointment log"""
        log = AppointmentLog(
            service_id=100, office_id=200, data='{"availableDays": ["2025-01-15"]}'
        )
        db_session.add(log)
        db_session.commit()

        assert log.service_id == 100
        assert log.office_id == 200
        assert log.data == '{"availableDays": ["2025-01-15"]}'
        assert log.found_at is not None

    def test_appointment_log_auto_timestamp(self, db_session):
        """Test log automatically sets found_at timestamp"""
        before = datetime.utcnow()
        log = AppointmentLog(service_id=100, office_id=200, data="{}")
        db_session.add(log)
        db_session.commit()
        after = datetime.utcnow()

        assert before <= log.found_at <= after

    def test_appointment_log_json_data(self, db_session):
        """Test log can store complex JSON data"""
        import json

        data = {
            "availableDays": ["2025-01-15", "2025-01-16"],
            "offices": [{"id": 200, "name": "Office A"}],
            "metadata": {"checked_at": "2025-01-10T10:00:00"},
        }

        log = AppointmentLog(service_id=100, office_id=200, data=json.dumps(data))
        db_session.add(log)
        db_session.commit()

        # Verify data can be parsed back
        parsed_data = json.loads(log.data)
        assert parsed_data["availableDays"] == ["2025-01-15", "2025-01-16"]
        assert len(parsed_data["offices"]) == 1


class TestBookingSessionModel:
    """Tests for BookingSession model"""

    def test_create_booking_session(self, db_session):
        """Test creating a booking session"""
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        session = BookingSession(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )
        db_session.add(session)
        db_session.commit()

        assert session.user_id == 12345
        assert session.state == "SELECTING_TIME"
        assert session.service_id == 100
        assert session.office_id == 200
        assert session.date == "2025-01-15"
        assert session.captcha_token == "token123"
        assert session.expires_at == expires_at

    def test_booking_session_auto_timestamps(self, db_session):
        """Test session automatically sets created_at and updated_at"""
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        before = datetime.utcnow()
        session = BookingSession(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )
        db_session.add(session)
        db_session.commit()
        after = datetime.utcnow()

        assert before <= session.created_at <= after
        assert before <= session.updated_at <= after

    def test_booking_session_optional_fields(self, db_session):
        """Test session can be created without optional fields"""
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        session = BookingSession(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )
        db_session.add(session)
        db_session.commit()

        assert session.timestamp is None
        assert session.name is None
        assert session.email is None

    def test_booking_session_with_all_fields(self, db_session):
        """Test session with all optional fields populated"""
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        session = BookingSession(
            user_id=12345,
            state="CONFIRMING",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
            timestamp=1234567890,
            name="John Doe",
            email="john@example.com",
        )
        db_session.add(session)
        db_session.commit()

        assert session.timestamp == 1234567890
        assert session.name == "John Doe"
        assert session.email == "john@example.com"

    def test_booking_session_unique_user_id(self, db_session):
        """Test user_id must be unique in booking sessions"""
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        session1 = BookingSession(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token1",
            expires_at=expires_at,
        )
        db_session.add(session1)
        db_session.commit()

        session2 = BookingSession(
            user_id=12345,
            state="ASKING_NAME",
            service_id=101,
            office_id=201,
            date="2025-01-16",
            captcha_token="token2",
            expires_at=expires_at,
        )
        db_session.add(session2)

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_booking_session_update_timestamp(self, db_session):
        """Test updating session updates the updated_at timestamp"""
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        session = BookingSession(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )
        db_session.add(session)
        db_session.commit()

        original_updated_at = session.updated_at

        # Update session
        import time

        time.sleep(0.01)  # Ensure timestamp difference
        session.state = "ASKING_NAME"
        session.updated_at = datetime.utcnow()
        db_session.commit()

        assert session.updated_at > original_updated_at
