"""
Type-safe data models for the bot
Uses dataclasses and enums for better type safety and IDE support
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from datetime import datetime


class Language(str, Enum):
    """Supported languages"""
    DE = "de"
    EN = "en"
    RU = "ru"


class Intent(str, Enum):
    """AI intent classification"""
    SERVICE_SEARCH = "service_search"
    INFORMATION_REQUEST = "information_request"


@dataclass
class ServiceInfo:
    """Information about a Munich service"""
    id: int
    name: str
    max_quantity: int = 1
    category: Optional[str] = None


@dataclass
class AIResponse:
    """Response from AI service matching"""
    intent: Intent
    suggested_services: List[int]
    explanation: str
    answer: str = ""


@dataclass
class UserSubscription:
    """User's service subscription"""
    user_id: int
    service_id: int
    office_id: int
    subscribed_at: datetime


@dataclass
class LanguageInfo:
    """Language metadata"""
    code: Language
    name: str
    flag: str


# Language metadata
LANGUAGE_INFO = {
    Language.DE: LanguageInfo(Language.DE, "Deutsch", "🇩🇪"),
    Language.EN: LanguageInfo(Language.EN, "English", "🇬🇧"),
    Language.RU: LanguageInfo(Language.RU, "Русский", "🇷🇺"),
}
