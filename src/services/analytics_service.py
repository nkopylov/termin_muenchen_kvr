"""
ABOUTME: Analytics service for tracking bot events to Umami
ABOUTME: Provides async event tracking without blocking bot operations
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import httpx

from src.config import get_config

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Track events to Umami analytics platform.

    Designed to be non-blocking - analytics errors never crash the bot.
    """

    def __init__(self):
        self.config = get_config()
        self.umami_url = self.config.umami_endpoint
        self.website_id = self.config.umami_website_id
        self.enabled = self.config.analytics_enabled
        self.client: Optional[httpx.AsyncClient] = None

        if self.enabled:
            self.client = httpx.AsyncClient(timeout=5.0)
            logger.info(f"Analytics enabled - tracking to {self.umami_url}")
        else:
            logger.info("Analytics disabled")

    async def track_event(
        self,
        event_name: str,
        user_id: Optional[int] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Track an event to Umami analytics.

        Args:
            event_name: Name of the event (e.g., "booking_completed")
            user_id: Telegram user ID (pseudonymous identifier)
            properties: Additional event properties (e.g., service_id, status)

        Note:
            This method never raises exceptions - analytics failures are logged only.
            The bot continues functioning even if analytics is completely broken.
        """
        if not self.enabled or self.client is None:
            return

        try:
            payload = {
                "payload": {
                    "hostname": "bot.alpenware.org",  # Virtual hostname for the bot
                    "screen": "1920x1080",  # Required by Umami
                    "language": "en-US",  # Required by Umami
                    "url": f"/event/{event_name}",  # Virtual URL for event
                    "referrer": "",  # Required by Umami
                    "title": event_name,  # Page title
                    "website": self.website_id,
                    "name": event_name,
                    "data": properties or {},
                },
                "type": "event"
            }

            # Add user_id as visitor identifier if provided
            if user_id:
                payload["payload"]["data"]["user_id"] = str(user_id)

            # Add timestamp
            payload["payload"]["data"]["timestamp"] = datetime.utcnow().isoformat()

            # Send async (don't block bot operations)
            response = await self.client.post(
                f"{self.umami_url}/api/send",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Munich-Appointment-Bot/2.0"
                }
            )

            if response.status_code != 200:
                logger.warning(
                    f"Umami tracking failed: {response.status_code} - {response.text}"
                )
            else:
                logger.info(f"✅ Tracked event: {event_name} (user_id: {user_id}, props: {properties})")
                logger.debug(f"Response: {response.text}")

        except httpx.TimeoutException:
            logger.warning(f"Analytics timeout for event: {event_name}")
        except Exception as e:
            # Never let analytics errors crash the bot
            logger.error(f"Analytics tracking error for {event_name}: {e}")

    async def close(self):
        """Close the HTTP client"""
        if self.client:
            await self.client.aclose()


# Singleton instance
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    """Get or create analytics service singleton"""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service


async def track_event(
    event_name: str,
    user_id: Optional[int] = None,
    **properties
) -> None:
    """
    Convenience function to track events.

    Usage:
        await track_event("booking_completed", user_id=123, status="success", duration_ms=45000)

    Args:
        event_name: Event name (e.g., "user_registered")
        user_id: Telegram user ID (optional)
        **properties: Event properties as keyword arguments
    """
    service = get_analytics_service()
    await service.track_event(event_name, user_id, properties)


async def cleanup_analytics():
    """
    Cleanup analytics service (close HTTP client).
    Call this on bot shutdown.
    """
    service = get_analytics_service()
    await service.close()
