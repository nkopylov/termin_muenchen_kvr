"""
Tests for repository layer (data access layer)
"""

from datetime import datetime, timedelta
from src.repositories import (
    UserRepository,
    SubscriptionRepository,
    AppointmentLogRepository,
    BookingSessionRepository,
)


class TestUserRepository:
    """Tests for UserRepository"""

    def test_create_user(self, db_session):
        """Test creating a new user"""
        repo = UserRepository(db_session)
        user = repo.create_user(
            user_id=12345,
            username="testuser",
            language="en",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )

        assert user.user_id == 12345
        assert user.username == "testuser"
        assert user.language == "en"
        assert user.start_date == "2025-01-01"
        assert user.end_date == "2025-12-31"

    def test_get_user(self, db_session):
        """Test retrieving a user by ID"""
        repo = UserRepository(db_session)
        repo.create_user(user_id=12345, username="testuser")

        user = repo.get_user(12345)
        assert user is not None
        assert user.user_id == 12345
        assert user.username == "testuser"

    def test_get_user_not_found(self, db_session):
        """Test retrieving non-existent user returns None"""
        repo = UserRepository(db_session)
        user = repo.get_user(99999)
        assert user is None

    def test_get_or_create_user_creates_new(self, db_session):
        """Test get_or_create creates user if not exists"""
        repo = UserRepository(db_session)
        user = repo.get_or_create_user(
            user_id=12345, username="testuser", language="de"
        )

        assert user.user_id == 12345
        assert user.username == "testuser"
        assert user.language == "de"

    def test_get_or_create_user_returns_existing(self, db_session):
        """Test get_or_create returns existing user"""
        repo = UserRepository(db_session)
        repo.create_user(user_id=12345, username="original")
        user2 = repo.get_or_create_user(user_id=12345, username="different")

        assert user2.user_id == 12345
        assert user2.username == "original"  # Original username preserved

    def test_set_date_range(self, db_session):
        """Test setting user's date range filter"""
        repo = UserRepository(db_session)
        repo.create_user(user_id=12345)

        repo.set_date_range(12345, "2025-01-01", "2025-12-31")
        user = repo.get_user(12345)
        assert user.start_date == "2025-01-01"
        assert user.end_date == "2025-12-31"

    def test_get_all_users(self, db_session):
        """Test retrieving all users"""
        repo = UserRepository(db_session)
        repo.create_user(user_id=1, username="user1")
        repo.create_user(user_id=2, username="user2")
        repo.create_user(user_id=3, username="user3")

        users = repo.get_all_users()
        assert len(users) == 3
        assert {u.user_id for u in users} == {1, 2, 3}

    def test_delete_user(self, db_session):
        """Test deleting a user"""
        repo = UserRepository(db_session)
        repo.create_user(user_id=12345)

        result = repo.delete_user(12345)
        assert result is True

        user = repo.get_user(12345)
        assert user is None

    def test_delete_user_not_found(self, db_session):
        """Test deleting non-existent user returns False"""
        repo = UserRepository(db_session)
        result = repo.delete_user(99999)
        assert result is False


class TestSubscriptionRepository:
    """Tests for SubscriptionRepository"""

    def test_add_subscription(self, db_session):
        """Test adding a service subscription"""
        # First create a user
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=12345)

        sub_repo = SubscriptionRepository(db_session)
        subscription = sub_repo.add_subscription(
            user_id=12345, service_id=100, office_id=200
        )

        assert subscription.user_id == 12345
        assert subscription.service_id == 100
        assert subscription.office_id == 200

    def test_add_subscription_duplicate(self, db_session):
        """Test adding duplicate subscription returns existing"""
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=12345)

        sub_repo = SubscriptionRepository(db_session)
        sub1 = sub_repo.add_subscription(user_id=12345, service_id=100, office_id=200)
        sub2 = sub_repo.add_subscription(user_id=12345, service_id=100, office_id=200)

        assert sub1.id == sub2.id  # Same subscription returned

    def test_remove_subscription(self, db_session):
        """Test removing a subscription"""
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=12345)

        sub_repo = SubscriptionRepository(db_session)
        sub_repo.add_subscription(user_id=12345, service_id=100, office_id=200)

        result = sub_repo.remove_subscription(user_id=12345, service_id=100)
        assert result is True

        subs = sub_repo.get_user_subscriptions(12345)
        assert len(subs) == 0

    def test_remove_subscription_not_found(self, db_session):
        """Test removing non-existent subscription returns False"""
        sub_repo = SubscriptionRepository(db_session)
        result = sub_repo.remove_subscription(user_id=12345, service_id=999)
        assert result is False

    def test_get_user_subscriptions(self, db_session):
        """Test retrieving user's subscriptions"""
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=12345)

        sub_repo = SubscriptionRepository(db_session)
        sub_repo.add_subscription(user_id=12345, service_id=100, office_id=200)
        sub_repo.add_subscription(user_id=12345, service_id=101, office_id=201)

        subs = sub_repo.get_user_subscriptions(12345)
        assert len(subs) == 2
        assert {s["service_id"] for s in subs} == {100, 101}
        assert {s["office_id"] for s in subs} == {200, 201}

    def test_get_all_service_subscriptions(self, db_session):
        """Test retrieving all subscriptions grouped by service/office"""
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=1)
        user_repo.create_user(user_id=2)
        user_repo.create_user(user_id=3)

        sub_repo = SubscriptionRepository(db_session)
        sub_repo.add_subscription(user_id=1, service_id=100, office_id=200)
        sub_repo.add_subscription(user_id=2, service_id=100, office_id=200)
        sub_repo.add_subscription(user_id=3, service_id=101, office_id=201)

        grouped = sub_repo.get_all_service_subscriptions()
        assert "100_200" in grouped
        assert set(grouped["100_200"]) == {1, 2}
        assert "101_201" in grouped
        assert set(grouped["101_201"]) == {3}

    def test_has_subscription(self, db_session):
        """Test checking if user has a subscription"""
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=12345)

        sub_repo = SubscriptionRepository(db_session)
        sub_repo.add_subscription(user_id=12345, service_id=100, office_id=200)

        assert sub_repo.has_subscription(12345, 100, 200) is True
        assert sub_repo.has_subscription(12345, 999, 999) is False

    def test_get_subscription_count(self, db_session):
        """Test getting count of user's subscriptions"""
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=12345)

        sub_repo = SubscriptionRepository(db_session)
        sub_repo.add_subscription(user_id=12345, service_id=100, office_id=200)
        sub_repo.add_subscription(user_id=12345, service_id=101, office_id=201)
        sub_repo.add_subscription(user_id=12345, service_id=102, office_id=202)

        count = sub_repo.get_subscription_count(12345)
        assert count == 3

    def test_delete_all_user_subscriptions(self, db_session):
        """Test deleting all subscriptions for a user"""
        user_repo = UserRepository(db_session)
        user_repo.create_user(user_id=12345)

        sub_repo = SubscriptionRepository(db_session)
        sub_repo.add_subscription(user_id=12345, service_id=100, office_id=200)
        sub_repo.add_subscription(user_id=12345, service_id=101, office_id=201)

        deleted_count = sub_repo.delete_all_user_subscriptions(12345)
        assert deleted_count == 2

        subs = sub_repo.get_user_subscriptions(12345)
        assert len(subs) == 0


class TestAppointmentLogRepository:
    """Tests for AppointmentLogRepository"""

    def test_log_appointment(self, db_session):
        """Test logging appointment availability"""
        repo = AppointmentLogRepository(db_session)
        data = {"availableDays": ["2025-01-15", "2025-01-16"]}

        log = repo.log_appointment(service_id=100, office_id=200, data=data)

        assert log.service_id == 100
        assert log.office_id == 200
        assert '"availableDays"' in log.data
        assert log.found_at is not None

    def test_get_recent_logs(self, db_session):
        """Test retrieving recent appointment logs"""
        repo = AppointmentLogRepository(db_session)

        # Create multiple logs
        repo.log_appointment(100, 200, {"day": "2025-01-15"})
        repo.log_appointment(101, 201, {"day": "2025-01-16"})
        repo.log_appointment(102, 202, {"day": "2025-01-17"})

        logs = repo.get_recent_logs(limit=10)
        assert len(logs) == 3

    def test_get_recent_logs_filtered_by_service(self, db_session):
        """Test retrieving logs filtered by service ID"""
        repo = AppointmentLogRepository(db_session)

        repo.log_appointment(100, 200, {"day": "2025-01-15"})
        repo.log_appointment(100, 201, {"day": "2025-01-16"})
        repo.log_appointment(999, 202, {"day": "2025-01-17"})

        logs = repo.get_recent_logs(service_id=100, limit=10)
        assert len(logs) == 2
        assert all(log.service_id == 100 for log in logs)

    def test_get_recent_logs_limit(self, db_session):
        """Test limit parameter in get_recent_logs"""
        repo = AppointmentLogRepository(db_session)

        # Create 5 logs
        for i in range(5):
            repo.log_appointment(100 + i, 200, {"index": i})

        logs = repo.get_recent_logs(limit=3)
        assert len(logs) == 3


class TestBookingSessionRepository:
    """Tests for BookingSessionRepository"""

    def test_create_session(self, db_session):
        """Test creating a booking session"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        session = repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )

        assert session.user_id == 12345
        assert session.state == "SELECTING_TIME"
        assert session.service_id == 100
        assert session.office_id == 200
        assert session.date == "2025-01-15"
        assert session.captcha_token == "token123"

    def test_create_session_deletes_existing(self, db_session):
        """Test creating session deletes any existing session for user"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        # Create first session
        repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token1",
            expires_at=expires_at,
        )

        # Create second session for same user
        repo.create_session(
            user_id=12345,
            state="ASKING_NAME",
            service_id=101,
            office_id=201,
            date="2025-01-16",
            captcha_token="token2",
            expires_at=expires_at,
        )

        # Only second session should exist
        current_session = repo.get_session(12345)
        assert current_session.state == "ASKING_NAME"
        assert current_session.service_id == 101

    def test_get_session(self, db_session):
        """Test retrieving a booking session"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )

        session = repo.get_session(12345)
        assert session is not None
        assert session.user_id == 12345

    def test_get_session_not_found(self, db_session):
        """Test retrieving non-existent session returns None"""
        repo = BookingSessionRepository(db_session)
        session = repo.get_session(99999)
        assert session is None

    def test_update_session(self, db_session):
        """Test updating booking session"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )

        updated = repo.update_session(
            user_id=12345,
            state="ASKING_NAME",
            timestamp=1234567890,
            name="John Doe",
            email="john@example.com",
        )

        assert updated.state == "ASKING_NAME"
        assert updated.timestamp == 1234567890
        assert updated.name == "John Doe"
        assert updated.email == "john@example.com"

    def test_update_session_partial(self, db_session):
        """Test partial update of booking session"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )

        # Update only name
        repo.update_session(user_id=12345, name="Jane Doe")

        session = repo.get_session(12345)
        assert session.name == "Jane Doe"
        assert session.state == "SELECTING_TIME"  # Unchanged

    def test_delete_session(self, db_session):
        """Test deleting a booking session"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )

        result = repo.delete_session(12345)
        assert result is True

        session = repo.get_session(12345)
        assert session is None

    def test_delete_session_not_found(self, db_session):
        """Test deleting non-existent session returns False"""
        repo = BookingSessionRepository(db_session)
        result = repo.delete_session(99999)
        assert result is False

    def test_is_user_in_booking(self, db_session):
        """Test checking if user has active booking session"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )

        assert repo.is_user_in_booking(12345) is True
        assert repo.is_user_in_booking(99999) is False

    def test_is_user_in_booking_expired(self, db_session):
        """Test expired session is not considered active"""
        repo = BookingSessionRepository(db_session)
        expires_at = datetime.utcnow() - timedelta(minutes=1)  # Expired 1 min ago

        repo.create_session(
            user_id=12345,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token123",
            expires_at=expires_at,
        )

        # Should return False and clean up expired session
        assert repo.is_user_in_booking(12345) is False
        assert repo.get_session(12345) is None

    def test_cleanup_expired_sessions(self, db_session):
        """Test cleaning up all expired sessions"""
        repo = BookingSessionRepository(db_session)
        now = datetime.utcnow()

        # Create 2 expired sessions
        repo.create_session(
            user_id=1,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token1",
            expires_at=now - timedelta(minutes=1),
        )
        repo.create_session(
            user_id=2,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token2",
            expires_at=now - timedelta(minutes=2),
        )

        # Create 1 active session
        repo.create_session(
            user_id=3,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token3",
            expires_at=now + timedelta(minutes=15),
        )

        deleted_count = repo.cleanup_expired_sessions()
        assert deleted_count == 2

        # Active session should still exist
        assert repo.get_session(3) is not None

    def test_get_all_active_sessions(self, db_session):
        """Test retrieving all active (non-expired) sessions"""
        repo = BookingSessionRepository(db_session)
        now = datetime.utcnow()

        # Create 2 active sessions
        repo.create_session(
            user_id=1,
            state="SELECTING_TIME",
            service_id=100,
            office_id=200,
            date="2025-01-15",
            captcha_token="token1",
            expires_at=now + timedelta(minutes=15),
        )
        repo.create_session(
            user_id=2,
            state="ASKING_NAME",
            service_id=101,
            office_id=201,
            date="2025-01-16",
            captcha_token="token2",
            expires_at=now + timedelta(minutes=10),
        )

        # Create 1 expired session
        repo.create_session(
            user_id=3,
            state="CONFIRMING",
            service_id=102,
            office_id=202,
            date="2025-01-17",
            captcha_token="token3",
            expires_at=now - timedelta(minutes=1),
        )

        active_sessions = repo.get_all_active_sessions()
        assert len(active_sessions) == 2
        assert {s.user_id for s in active_sessions} == {1, 2}
