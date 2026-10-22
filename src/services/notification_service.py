"""
Notification service for sending appointment availability alerts to users.
Handles both initial notifications and progressive updates with time slots.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from src.config import get_config
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.services.analytics_service import track_event
from src.services.queue_manager import is_user_in_queue
from src.termin_tracker import get_available_slots

logger = logging.getLogger(__name__)


def format_available_appointments(data, lang: str = "en") -> str:
    """Format available appointments data for display"""
    if not data:
        return ""

    result = ""

    # Handle Munich API format with time slots
    if isinstance(data, dict) and "slots_by_date" in data:
        slots_by_date = data["slots_by_date"]
        available_days = data.get("availableDays", [])

        if slots_by_date:
            # Show dates with time slots
            for date, times in list(slots_by_date.items())[:5]:
                if times:
                    # Show first 5 time slots
                    time_str = ", ".join(times[:5])
                    result += f"📅 {date}: {time_str}\n"
                else:
                    # Date available but no time slots fetched
                    result += f"📅 {date}\n"

            # Show remaining days count
            remaining = len(available_days) - len(slots_by_date)
            if remaining > 0:
                result += t("notify.more_days", lang, count=remaining) + "\n"

        return result.strip()

    # Handle Munich API format without slots: {'availableDays': [{'date': '2025-10-13', 'providerIDs': '10461', 'offices': [...]}]}
    if isinstance(data, dict) and "availableDays" in data:
        available_days = data["availableDays"]
        if available_days:
            for day in available_days[:5]:
                date = day.get("date", t("notify.unknown_date", lang))
                result += f"📅 {date}\n"
            if len(available_days) > 5:
                result += (
                    t("notify.more_days", lang, count=len(available_days) - 5) + "\n"
                )
        return result.strip()

    # Legacy format handling
    if isinstance(data, dict):
        for date, times in data.items():
            if times:
                # Handle times as list of strings or list of dicts
                if isinstance(times, list):
                    time_strs = []
                    for entry in times[:3]:
                        if isinstance(entry, dict):
                            # Extract time from dict (e.g., {'time': '09:00', ...})
                            time_strs.append(
                                str(entry.get("time", entry.get("slot", str(entry))))
                            )
                        else:
                            time_strs.append(str(entry))
                    result += f"📅 {date}: {', '.join(time_strs)}\n"
                else:
                    result += f"📅 {date}: {times}\n"
    elif isinstance(data, list):
        for item in data[:5]:
            if isinstance(item, dict) and "date" in item:
                result += f"📅 {item['date']}\n"
            elif isinstance(item, str):
                result += f"📅 {item}\n"

    return result.strip()


def _format_initial_dates(available_days: list[dict], lang: str) -> str:
    """List the first 5 available dates, followed by how many more there are."""
    dates = "\n".join([f"📅 {day.get('date')}" for day in available_days[:5]])
    if len(available_days) > 5:
        dates += "\n" + t("notify.more_days", lang, count=len(available_days) - 5)
    return dates


def _booking_keyboard(
    available_days: list[dict],
    office_id: int,
    service_id: int,
    booking_url: str,
    lang: str,
) -> InlineKeyboardMarkup | None:
    """Booking buttons for each available date plus a link to the website."""
    # Create inline keyboard with booking buttons for each available date
    keyboard = []
    for day_info in available_days[:5]:  # Show first 5 dates
        date = day_info.get("date")
        if date:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        t("notify.btn_book_date", lang, date=date),
                        callback_data=f"book_{date}_{office_id}_{service_id}",
                    )
                ]
            )

    # Add link to manual booking
    keyboard.append(
        [InlineKeyboardButton(t("notify.btn_book_manually", lang), url=booking_url)]
    )

    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def notify_users_of_appointment(
    application: Application,
    user_ids: list[int],
    service_id: int,
    office_id: int,
    service_name: str,
    data: dict,
    captcha_token: str,
) -> None:
    """
    Notify users about available appointments with progressive updates.

    Args:
        application: Telegram Application instance
        user_ids: List of user IDs to notify
        service_id: Service ID
        office_id: Office ID
        service_name: Human-readable service name
        data: Appointment availability data from API
        captcha_token: Valid captcha token for fetching time slots
    """
    config = get_config()
    booking_url = config.get_booking_url_for_service(service_id, office_id)
    available_days = data.get("availableDays", [])

    # STEP 1: Send immediate notification with dates only
    # Send initial messages and store message IDs for updating
    message_ids = {}
    user_languages: dict[int, str] = {}
    for user_id in user_ids:
        # Skip users currently in booking conversation
        if is_user_in_queue(user_id):
            logger.info(
                f"Skipping notification for user {user_id} - booking in progress"
            )
            continue

        lang = get_user_language(user_id)
        user_languages[user_id] = lang
        initial_message = t(
            "notify.initial",
            lang,
            service_name=service_name,
            dates=_format_initial_dates(available_days, lang),
            booking_url=booking_url,
        )

        try:
            sent_msg = await application.bot.send_message(
                chat_id=user_id,
                text=initial_message,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            message_ids[user_id] = sent_msg.message_id
            logger.info(f"Sent initial notification to user {user_id}")

            # Track notification sent
            await track_event(
                "notification_sent",
                user_id=user_id,
                service_id=service_id,
                service_name=service_name,
                notification_type="initial",
                slots_count=len(available_days),
            )
        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"Failed to send initial notification to user {user_id}: {e}")

            # Determine error type
            if "blocked" in error_str or "bot was blocked by the user" in error_str:
                error_type = "user_blocked_bot"

                # Track user blocked bot
                await track_event(
                    "user_blocked_bot",
                    user_id=user_id,
                    last_command_timestamp=datetime.utcnow().isoformat(),
                )
            elif "rate" in error_str or "too many requests" in error_str:
                error_type = "rate_limit_exceeded"
            else:
                error_type = "telegram_api_error"

            # Track notification failure
            await track_event(
                "notification_failed",
                user_id=user_id,
                service_id=service_id,
                error_type=error_type,
            )

    # STEP 2: Fetch time slots and build slots_by_date
    slots_by_date = {}  # {date: [time slots]}
    for day_info in available_days[:5]:
        date = day_info.get("date")
        if date:
            slots_data = get_available_slots(
                date, str(office_id), str(service_id), captcha_token
            )
            if slots_data and isinstance(slots_data, dict):
                # New API format: {"offices": [{"officeId": X, "appointments": [timestamps]}]}
                offices = slots_data.get("offices", [])
                logger.debug(f"Slots API response for {date}: {slots_data}")
                if offices:
                    # Get appointments from first office (we only query one)
                    appointments_timestamps = offices[0].get("appointments", [])
                    if appointments_timestamps:
                        # Convert Unix timestamps to HH:MM format (show first 5)
                        # Use Europe/Berlin timezone for Munich appointments
                        times = []
                        for ts in appointments_timestamps[:5]:
                            dt = datetime.fromtimestamp(
                                ts, tz=ZoneInfo("Europe/Berlin")
                            )
                            times.append(dt.strftime("%H:%M"))
                        slots_by_date[date] = times
                        logger.debug(
                            f"Fetched {len(appointments_timestamps)} slots for {date}, showing first 5: {times}"
                        )
                    else:
                        slots_by_date[date] = []
                else:
                    slots_by_date[date] = []
            else:
                # Fallback: just show the date without times
                slots_by_date[date] = []

    # Update data to include slots
    data["slots_by_date"] = slots_by_date
    logger.info(f"📋 Slots by date: {slots_by_date}")

    # STEP 3: Update all messages with final time slot information
    # Store captcha token in bot_data for booking flow
    application.bot_data["captcha_token"] = captcha_token

    # Update all messages with time slots and booking buttons
    for user_id, msg_id in message_ids.items():
        lang = user_languages[user_id]
        appointments_detail = format_available_appointments(data, lang)
        final_message = t(
            "notify.final",
            lang,
            service_name=service_name,
            dates=appointments_detail or _format_initial_dates(available_days, lang),
            booking_url=booking_url,
        )
        reply_markup = _booking_keyboard(
            available_days, office_id, service_id, booking_url, lang
        )

        try:
            await application.bot.edit_message_text(
                chat_id=user_id,
                message_id=msg_id,
                text=final_message,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=reply_markup,
            )
            logger.info(
                f"Updated message for user {user_id} with time slots and booking buttons"
            )
        except Exception as e:
            logger.error(f"Failed to update message for user {user_id}: {e}")
