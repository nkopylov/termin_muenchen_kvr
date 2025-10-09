"""
Type-safe data models for the bot
Uses dataclasses and enums for better type safety and IDE support
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class ServiceInfo:
    """Information about a Munich service"""
    id: int
    name: str
    max_quantity: int = 1
    category: Optional[str] = None


@dataclass
class UserSubscription:
    """User's service subscription"""
    user_id: int
    service_id: int
    office_id: int
    subscribed_at: datetime
