"""
Database models using SQLModel
Provides type-safe ORM with Pydantic validation
"""

from datetime import datetime

from pydantic import NaiveDatetime
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    """User database model"""

    __tablename__ = "users"

    user_id: int = Field(primary_key=True)
    username: str | None = Field(default=None, max_length=255)
    subscribed_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
    start_date: str | None = Field(default=None, max_length=10)
    end_date: str | None = Field(default=None, max_length=10)
    language: str = Field(default="", max_length=2)
    booking_name: str | None = Field(default=None, max_length=255)
    booking_email: str | None = Field(default=None, max_length=255)
    # Current navigation screen message, see src/ui/screens.py
    nav_message_id: int | None = None
    # 0 = never saw the reply keyboard UI, 1 = chat command list set, 2 = reply keyboard delivered
    ui_version: int = Field(default=0, sa_column_kwargs={"server_default": "0"})

    # Relationships
    subscriptions: list["ServiceSubscription"] = Relationship(back_populates="user")


class ServiceSubscription(SQLModel, table=True):
    """Service subscription database model"""

    __tablename__ = "service_subscriptions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", index=True)
    service_id: int = Field(index=True)
    office_id: int
    subscribed_at: NaiveDatetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User | None = Relationship(back_populates="subscriptions")

    class Config:
        # Unique constraint on user_id, service_id, office_id
        table_args = ({"sqlite_autoincrement": True},)


class AppointmentLog(SQLModel, table=True):
    """Appointment availability log"""

    __tablename__ = "appointment_logs"

    id: int | None = Field(default=None, primary_key=True)
    found_at: NaiveDatetime = Field(default_factory=datetime.utcnow, index=True)
    service_id: int = Field(index=True)
    office_id: int
    data: str  # JSON string of appointment data

    class Config:
        table_args = ({"sqlite_autoincrement": True},)


class BookingSession(SQLModel, table=True):
    """Booking conversation session state"""

    __tablename__ = "booking_sessions"

    user_id: int = Field(primary_key=True)
    state: str = Field(
        max_length=50
    )  # SELECTING_TIME, ASKING_NAME, ASKING_EMAIL, CONFIRMING
    service_id: int
    office_id: int
    date: str = Field(max_length=10)  # YYYY-MM-DD
    captcha_token: str = Field(max_length=500)

    # Booking data (collected during conversation)
    timestamp: int | None = Field(default=None)  # Unix timestamp of selected slot
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)

    # Watch whose alert started the booking; None for buttons of messages without a watch
    watch_id: int | None = None
    # Latest booking message that carries buttons
    message_id: int | None = None

    # Metadata
    created_at: NaiveDatetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
    expires_at: NaiveDatetime  # Auto-cleanup after expiry

    class Config:
        table_args = ({"sqlite_autoincrement": True},)


class Watch(SQLModel, table=True):
    """A user's search for free appointments of one service"""

    __tablename__ = "watches"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", index=True)
    service_id: int = Field(index=True)
    office_id: int | None = None  # None = all public offices of the service

    # "when", see src/watches/when.py
    when_kind: str = Field(max_length=8)  # "asap" | "within" | "before" | "between"
    within_days: int | None = None  # only for "within"
    date_from: str | None = Field(default=None, max_length=10)  # ISO, only "between"
    # ISO; "before": exclusive deadline, "between": inclusive end
    date_to: str | None = Field(default=None, max_length=10)

    # lifecycle
    # "active" | "paused" | "ended"
    status: str = Field(default="active", max_length=8, index=True)
    # "user" | "blocked", only when paused
    pause_reason: str | None = Field(default=None, max_length=8)
    # "deadline" | "booked" | "stopped" | "gone", only when ended
    end_reason: str | None = Field(default=None, max_length=8)
    created_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
    updated_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
    ended_at: NaiveDatetime | None = None

    # last check
    last_checked_at: NaiveDatetime | None = None
    last_snapshot: str | None = None  # JSON of WatchSnapshot

    # live alert message; alert_chat_id and alert_message_id both None = no live alert
    alerted_slots: str = "[]"  # JSON list of slot keys already alerted
    alert_chat_id: int | None = None
    alert_message_id: int | None = Field(default=None, index=True)
    # "slots" | "empty" | "ended"
    alert_kind: str | None = Field(default=None, max_length=8)
    alert_sent_at: NaiveDatetime | None = None
    alert_shown_slots: str = "[]"  # JSON list of slot keys rendered in the live alert
    alert_render_hash: str | None = Field(default=None, max_length=40)
    alert_interacted_at: NaiveDatetime | None = None


class PendingRetire(SQLModel, table=True):
    """A message whose buttons must be removed once it is no longer in use"""

    __tablename__ = "pending_retires"
    __table_args__ = (UniqueConstraint("chat_id", "message_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    chat_id: int
    message_id: int
    text: str  # final HTML the message is edited to
    not_before: NaiveDatetime = Field(index=True)
    attempts: int = 0
    created_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
