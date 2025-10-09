"""
Repository pattern for database access
Provides clean separation between business logic and data access
"""

from sqlmodel import Session, select, delete
from typing import List, Optional, Dict
from datetime import datetime
import json

from src.db_models import User, ServiceSubscription, AppointmentLog, BookingSession


class UserRepository:
    """Repository for User operations"""

    def __init__(self, session: Session):
        self.session = session

    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return self.session.get(User, user_id)

    def create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        language: str = "de",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> User:
        """Create new user"""
        user = User(
            user_id=user_id,
            username=username,
            language=language,
            start_date=start_date,
            end_date=end_date,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_or_create_user(
        self, user_id: int, username: Optional[str] = None, language: str = "de"
    ) -> User:
        """Get existing user or create new one"""
        user = self.get_user(user_id)
        if user is None:
            user = self.create_user(user_id, username, language)
        return user

    def get_user_language(self, user_id: int) -> str:
        """Get user's preferred language"""
        user = self.get_user(user_id)
        return user.language if user else "de"

    def set_user_language(self, user_id: int, language: str) -> None:
        """Set user's language preference"""
        user = self.get_or_create_user(user_id)
        user.language = language
        self.session.commit()

    def set_date_range(
        self, user_id: int, start_date: Optional[str], end_date: Optional[str]
    ) -> None:
        """Set user's date range for appointments"""
        user = self.get_or_create_user(user_id)
        user.start_date = start_date
        user.end_date = end_date
        self.session.commit()

    def get_all_users(self) -> List[User]:
        """Get all users"""
        statement = select(User)
        return list(self.session.exec(statement))

    def delete_user(self, user_id: int) -> bool:
        """Delete user and all their subscriptions"""
        user = self.get_user(user_id)
        if user:
            self.session.delete(user)
            self.session.commit()
            return True
        return False


class SubscriptionRepository:
    """Repository for ServiceSubscription operations"""

    def __init__(self, session: Session):
        self.session = session

    def add_subscription(
        self, user_id: int, service_id: int, office_id: int
    ) -> ServiceSubscription:
        """Add a service subscription for a user"""
        # Check if already exists
        statement = select(ServiceSubscription).where(
            ServiceSubscription.user_id == user_id,
            ServiceSubscription.service_id == service_id,
            ServiceSubscription.office_id == office_id,
        )
        existing = self.session.exec(statement).first()

        if existing:
            return existing

        subscription = ServiceSubscription(
            user_id=user_id, service_id=service_id, office_id=office_id
        )
        self.session.add(subscription)
        self.session.commit()
        self.session.refresh(subscription)
        return subscription

    def remove_subscription(self, user_id: int, service_id: int) -> bool:
        """Remove a user's subscription to a service"""
        statement = delete(ServiceSubscription).where(
            ServiceSubscription.user_id == user_id,
            ServiceSubscription.service_id == service_id,
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount > 0

    def get_user_subscriptions(self, user_id: int) -> List[Dict]:
        """Get all subscriptions for a user"""
        statement = select(ServiceSubscription).where(
            ServiceSubscription.user_id == user_id
        )
        subscriptions = self.session.exec(statement).all()

        return [
            {
                "service_id": sub.service_id,
                "office_id": sub.office_id,
                "subscribed_at": sub.subscribed_at.isoformat(),
            }
            for sub in subscriptions
        ]

    def get_all_service_subscriptions(self) -> Dict[str, List[int]]:
        """
        Get all unique service/office combinations and their subscribers

        Returns:
            Dict mapping "service_id_office_id" to list of user_ids
        """
        statement = select(ServiceSubscription)
        all_subs = self.session.exec(statement).all()

        # Group by service_id and office_id
        grouped: Dict[str, List[int]] = {}
        for sub in all_subs:
            key = f"{sub.service_id}_{sub.office_id}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(sub.user_id)

        return grouped

    def has_subscription(self, user_id: int, service_id: int, office_id: int) -> bool:
        """Check if user has a specific subscription"""
        statement = select(ServiceSubscription).where(
            ServiceSubscription.user_id == user_id,
            ServiceSubscription.service_id == service_id,
            ServiceSubscription.office_id == office_id,
        )
        return self.session.exec(statement).first() is not None

    def get_subscription_count(self, user_id: int) -> int:
        """Get count of user's subscriptions"""
        statement = select(ServiceSubscription).where(
            ServiceSubscription.user_id == user_id
        )
        return len(list(self.session.exec(statement)))

    def delete_all_user_subscriptions(self, user_id: int) -> int:
        """Delete all subscriptions for a user"""
        statement = delete(ServiceSubscription).where(
            ServiceSubscription.user_id == user_id
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount


class AppointmentLogRepository:
    """Repository for AppointmentLog operations"""

    def __init__(self, session: Session):
        self.session = session

    def log_appointment(
        self, service_id: int, office_id: int, data: Dict
    ) -> AppointmentLog:
        """Log appointment availability"""
        log = AppointmentLog(
            service_id=service_id, office_id=office_id, data=json.dumps(data)
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return log

    def get_recent_logs(
        self, service_id: Optional[int] = None, limit: int = 100
    ) -> List[AppointmentLog]:
        """Get recent appointment logs"""
        statement = select(AppointmentLog).order_by(AppointmentLog.found_at.desc())

        if service_id:
            statement = statement.where(AppointmentLog.service_id == service_id)

        statement = statement.limit(limit)
        return list(self.session.exec(statement))


class BookingSessionRepository:
    """Repository for BookingSession operations"""

    def __init__(self, session: Session):
        self.session = session

    def create_session(
        self,
        user_id: int,
        state: str,
        service_id: int,
        office_id: int,
        date: str,
        captcha_token: str,
        expires_at: datetime,
    ) -> BookingSession:
        """Create a new booking session"""
        # Delete any existing session for this user first
        self.delete_session(user_id)

        session = BookingSession(
            user_id=user_id,
            state=state,
            service_id=service_id,
            office_id=office_id,
            date=date,
            captcha_token=captcha_token,
            expires_at=expires_at,
        )
        self.session.add(session)
        self.session.commit()
        self.session.refresh(session)
        return session

    def get_session(self, user_id: int) -> Optional[BookingSession]:
        """Get booking session for a user"""
        return self.session.get(BookingSession, user_id)

    def update_session(
        self,
        user_id: int,
        state: Optional[str] = None,
        timestamp: Optional[int] = None,
        name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Optional[BookingSession]:
        """Update booking session"""
        booking_session = self.get_session(user_id)
        if not booking_session:
            return None

        if state is not None:
            booking_session.state = state
        if timestamp is not None:
            booking_session.timestamp = timestamp
        if name is not None:
            booking_session.name = name
        if email is not None:
            booking_session.email = email

        booking_session.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(booking_session)
        return booking_session

    def delete_session(self, user_id: int) -> bool:
        """Delete booking session"""
        session = self.get_session(user_id)
        if session:
            self.session.delete(session)
            self.session.commit()
            return True
        return False

    def is_user_in_booking(self, user_id: int) -> bool:
        """Check if user has an active booking session"""
        session = self.get_session(user_id)
        if not session:
            return False

        # Check if expired
        if datetime.utcnow() > session.expires_at:
            self.delete_session(user_id)
            return False

        return True

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions"""
        statement = delete(BookingSession).where(
            BookingSession.expires_at < datetime.utcnow()
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount

    def get_all_active_sessions(self) -> List[BookingSession]:
        """Get all active (non-expired) sessions"""
        statement = select(BookingSession).where(
            BookingSession.expires_at > datetime.utcnow()
        )
        return list(self.session.exec(statement))
