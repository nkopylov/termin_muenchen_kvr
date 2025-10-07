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
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # Required settings
    telegram_bot_token: str = Field(
        ...,
        description="Telegram Bot API token from @BotFather"
    )

    # Optional Telegram settings
    admin_telegram_id: Optional[int] = Field(
        None,
        description="Admin user ID for alerts and health checks"
    )

    # OpenAI API settings (optional - fallback to keyword matching if not set)
    openai_api_key: Optional[str] = Field(
        None,
        description="OpenAI API key for AI-powered features"
    )
    openai_model: str = Field(
        "gpt-4o-mini",
        description="OpenAI model to use"
    )
    openai_api_url: str = Field(
        "https://api.openai.com/v1/chat/completions",
        description="OpenAI API endpoint URL"
    )

    # Database settings
    db_file: str = Field(
        "bot_data.db",
        description="SQLite database file path"
    )

    # Munich appointment system settings
    office_id: str = Field(
        "10461",
        description="Default Munich office ID"
    )
    check_interval: int = Field(
        15,
        ge=5,
        le=600,
        description="Interval in seconds between appointment checks (default: 15)"
    )

    @field_validator('telegram_bot_token')
    @classmethod
    def validate_telegram_token(cls, v: str) -> str:
        """Validate Telegram bot token format"""
        if not v or v == "your_bot_token_here":
            raise ValueError(
                "TELEGRAM_BOT_TOKEN must be set to a valid token from @BotFather"
            )
        if ':' not in v:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN appears to be invalid (should contain ':')"
            )
        return v

    @field_validator('check_interval')
    @classmethod
    def validate_check_interval(cls, v: int) -> int:
        """Ensure check interval is reasonable"""
        if v < 5:
            raise ValueError("check_interval must be at least 5 seconds")
        if v > 600:
            raise ValueError("check_interval must be at most 600 seconds (10 minutes)")
        return v

    @property
    def has_openai(self) -> bool:
        """Check if OpenAI API is configured"""
        return self.openai_api_key is not None and self.openai_api_key != ""

    @property
    def booking_url(self) -> str:
        """Generate booking URL for a service"""
        return f"https://stadt.muenchen.de/buergerservice/terminvereinbarung.html"

    def get_booking_url_for_service(self, service_id: int, office_id: Optional[int] = None) -> str:
        """Generate booking URL for a specific service and office"""
        office = office_id or self.office_id
        return f"https://stadt.muenchen.de/buergerservice/terminvereinbarung.html#/services/{service_id}/locations/{office}"


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


def reload_config() -> BotConfig:
    """Force reload configuration from environment"""
    global _config
    _config = BotConfig()
    return _config
