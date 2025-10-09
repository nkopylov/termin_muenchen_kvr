"""
Type-safe configuration using Pydantic Settings
Validates environment variables and provides sensible defaults
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class BotConfig(BaseSettings):
    """
    Bot configuration with validation
    Automatically loads from environment variables and .env file
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Required settings
    telegram_bot_token: str = Field(
        ..., description="Telegram Bot API token from @BotFather"
    )

    # Optional Telegram settings
    admin_telegram_id: Optional[int] = Field(
        None, description="Admin user ID for alerts and health checks"
    )

    # Database settings
    db_file: str = Field("bot_data.db", description="SQLite database file path")

    # Munich appointment system settings
    check_interval: int = Field(
        120,
        ge=5,
        le=600,
        description="Interval in seconds between appointment checks (default: 120)",
    )

    @field_validator("telegram_bot_token")
    @classmethod
    def validate_telegram_token(cls, v: str) -> str:
        """Validate Telegram bot token format"""
        if not v or v == "your_bot_token_here":
            raise ValueError(
                "TELEGRAM_BOT_TOKEN must be set to a valid token from @BotFather"
            )
        if ":" not in v:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN appears to be invalid (should contain ':')"
            )
        return v

    def get_booking_url_for_service(self, service_id: int, office_id: int) -> str:
        """Generate booking URL for a specific service and office"""
        return f"https://stadt.muenchen.de/buergerservice/terminvereinbarung.html#/services/{service_id}/locations/{office_id}"


# Singleton instance
_config: Optional[BotConfig] = None


def get_config() -> BotConfig:
    """
    Get or create the global configuration instance

    Returns:
        BotConfig: Validated configuration

    Raises:
        ValidationError: If configuration is invalid
    """
    global _config
    if _config is None:
        _config = BotConfig()
    return _config
