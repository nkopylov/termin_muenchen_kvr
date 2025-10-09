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
        table_args = (
            {"sqlite_autoincrement": True},
        )


class AppointmentLog(SQLModel, table=True):
    """Appointment availability log"""
    __tablename__ = "appointment_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    found_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    service_id: int = Field(index=True)
    office_id: int
    data: str  # JSON string of appointment data

    class Config:
        table_args = (
            {"sqlite_autoincrement": True},
        )
