"""
Database models using SQLModel
Provides type-safe ORM with Pydantic validation
"""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime


class User(SQLModel, table=True):
    """User database model"""

    __tablename__ = "users"

    user_id: int = Field(primary_key=True)
    username: Optional[str] = Field(default=None, max_length=255)
    subscribed_at: datetime = Field(default_factory=datetime.utcnow)
    start_date: Optional[str] = Field(default=None, max_length=10)
    end_date: Optional[str] = Field(default=None, max_length=10)
    language: str = Field(default="de", max_length=2)

    # Relationships
    subscriptions: List["ServiceSubscription"] = Relationship(back_populates="user")


class ServiceSubscription(SQLModel, table=True):
    """Service subscription database model"""

    __tablename__ = "service_subscriptions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", index=True)
    service_id: int = Field(index=True)
    office_id: int
    subscribed_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: Optional[User] = Relationship(back_populates="subscriptions")

    class Config:
        # Unique constraint on user_id, service_id, office_id
        table_args = ({"sqlite_autoincrement": True},)


class AppointmentLog(SQLModel, table=True):
    """Appointment availability log"""

    __tablename__ = "appointment_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    found_at: datetime = Field(default_factory=datetime.utcnow, index=True)
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
    timestamp: Optional[int] = Field(default=None)  # Unix timestamp of selected slot
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime  # Auto-cleanup after expiry

    class Config:
        table_args = ({"sqlite_autoincrement": True},)
