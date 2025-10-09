"""
Appointment checker service - background task for monitoring appointment availability.
Coordinates captcha token management, database queries, and user notifications.
"""

import time
import asyncio
import logging
from datetime import datetime
from telegram.ext import Application

from src.config import get_config
from src.database import get_session
from src.repositories import (
    SubscriptionRepository,
    AppointmentLogRepository,
    BookingSessionRepository,
)
from src.termin_tracker import get_fresh_captcha_token, get_available_days
from src.services_manager import get_service_info
from src.services.notification_service import notify_users_of_appointment

logger = logging.getLogger(__name__)

# Global stats tracking
stats = {
    "total_checks": 0,
    "successful_checks": 0,
    "failed_checks": 0,
    "appointments_found_count": 0,
    "last_check_time": None,
    "last_success_time": None,
    "bot_start_time": None,
}

# Captcha token management
captcha_token = None
token_expires_at = 0


def get_stats() -> dict:
    """Get current statistics"""
    return stats


def set_bot_start_time() -> None:
    """Set bot start time in stats"""
    stats["bot_start_time"] = datetime.now()


def get_user_date_range(user_id: int) -> tuple[str | None, str | None]:
    """
    Get user's date range preference from database.

    Args:
        user_id: Telegram user ID

    Returns:
        Tuple of (start_date, end_date) or (None, None)
    """
    from src.repositories import UserRepository
    from datetime import timedelta

    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if not user:
            return None, None

        start_date = user.start_date
        end_date = user.end_date

        # Default to next 60 days if not set
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        if not end_date:
            end_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")

        return start_date, end_date


async def send_health_alert(application: Application, message: str) -> None:
    """Send health alert to admin if configured"""
    config = get_config()
    if config.admin_telegram_id:
        try:
            await application.bot.send_message(
                chat_id=config.admin_telegram_id,
                text=f"⚠️ <b>Health Alert</b>\n\n{message}",
                parse_mode="HTML",
            )
            logger.info(f"Sent health alert to admin {config.admin_telegram_id}")
        except Exception as e:
            logger.error(f"Failed to send health alert: {e}")


async def check_and_notify(application: Application) -> None:
    """
    Background task to check for appointments and notify subscribers.
    Runs continuously in a loop, checking all service subscriptions.
    """
    global captcha_token, token_expires_at

    config = get_config()
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5

    while True:
        try:
            stats["last_check_time"] = datetime.now()
            stats["total_checks"] += 1

            # Clean up expired booking sessions periodically (every 5 checks)
            if stats["total_checks"] % 5 == 0:
                with get_session() as session:
                    booking_repo = BookingSessionRepository(session)
                    expired_count = booking_repo.cleanup_expired_sessions()
                    if expired_count > 0:
                        logger.info(
                            f"Cleaned up {expired_count} expired booking session(s)"
                        )

            # Get all service subscriptions using repository
            with get_session() as session:
                sub_repo = SubscriptionRepository(session)
                service_subs = sub_repo.get_all_service_subscriptions()

            if not service_subs:
                logger.info("No service subscriptions, skipping check")
                await asyncio.sleep(config.check_interval)
                continue

            # Refresh token if needed
            if time.time() >= token_expires_at:
                logger.info("Getting fresh captcha token (in thread pool)...")
                captcha_token = await get_fresh_captcha_token()
                if not captcha_token:
                    logger.error("Failed to get captcha token")
                    stats["failed_checks"] += 1
                    consecutive_failures += 1

                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        await send_health_alert(
                            application,
                            f"Bot has failed {consecutive_failures} consecutive checks!\n"
                            f"Last error: Failed to get captcha token",
                        )

                    await asyncio.sleep(config.check_interval)
                    continue
                token_expires_at = time.time() + 280  # ~4.5 minutes
                logger.info("Got fresh token (solved in background thread)")

            # Check each unique service/office combination
            for service_office_key, user_ids in service_subs.items():
                service_id, office_id = service_office_key.split("_")
                service_id = int(service_id)
                office_id = int(office_id)

                # Get date ranges for users subscribed to this service
                date_ranges = {}
                for user_id in user_ids:
                    start_date, end_date = get_user_date_range(user_id)
                    if start_date and end_date:
                        key = f"{start_date}_{end_date}"
                        if key not in date_ranges:
                            date_ranges[key] = []
                        date_ranges[key].append(user_id)

                # Check each unique date range for this service
                for date_key, date_user_ids in date_ranges.items():
                    start_date, end_date = date_key.split("_")

                    # Get service name for logging
                    service_info = get_service_info(service_id)
                    service_name = (
                        service_info["name"]
                        if service_info
                        else f"Service {service_id}"
                    )

                    logger.info(
                        f"Checking {service_name} (ID:{service_id}, Office:{office_id}) from {start_date} to {end_date} for {len(date_user_ids)} users"
                    )
                    data = get_available_days(
                        start_date,
                        end_date,
                        captcha_token,
                        str(office_id),
                        str(service_id),
                    )

                    # Check if appointments are available
                    appointments_found = False

                    if isinstance(data, dict):
                        if "errorCode" in data:
                            logger.warning(
                                f"API error: {data['errorCode']} - {data.get('errorMessage', '')}"
                            )
                            stats["failed_checks"] += 1
                            consecutive_failures += 1
                        elif data and len(data) > 0:
                            # Extract available days from response
                            available_days = data.get("availableDays", [])
                            if available_days:
                                appointments_found = True
                    elif isinstance(data, list) and len(data) > 0:
                        appointments_found = True

                    if appointments_found:
                        logger.info(
                            f"✅ Appointments found for {service_name}! Notifying {len(date_user_ids)} users"
                        )
                        logger.info(f"📋 Full API response: {data}")
                        stats["successful_checks"] += 1
                        stats["last_success_time"] = datetime.now()
                        stats["appointments_found_count"] += 1
                        consecutive_failures = 0

                        # Log the appointment with repository
                        with get_session() as session:
                            log_repo = AppointmentLogRepository(session)
                            log_repo.log_appointment(service_id, office_id, data)

                        # Notify all subscribed users
                        await notify_users_of_appointment(
                            application=application,
                            user_ids=date_user_ids,
                            service_id=service_id,
                            office_id=office_id,
                            service_name=service_name,
                            data=data,
                            captcha_token=captcha_token,
                        )
                    else:
                        logger.info(
                            f"No appointments available for {service_name} ({start_date} to {end_date})"
                        )
                        stats["successful_checks"] += 1
                        stats["last_success_time"] = datetime.now()
                        consecutive_failures = 0

        except Exception as e:
            logger.error(f"Error in check_and_notify: {e}")
            stats["failed_checks"] += 1
            consecutive_failures += 1

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                await send_health_alert(
                    application,
                    f"Bot has failed {consecutive_failures} consecutive checks!\n"
                    f"Last error: {str(e)}",
                )

        await asyncio.sleep(config.check_interval)
