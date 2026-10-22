"""
/status command - Show user's current status and settings
"""

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.config import get_config
from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import (
    AppointmentLogRepository,
    SubscriptionRepository,
    UserRepository,
)
from src.services.appointment_checker import get_stats, get_user_date_range

logger = logging.getLogger(__name__)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot status"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        log_repo = AppointmentLogRepository(session)

        user = user_repo.get_user(user_id)
        if not user:
            await update.message.reply_text(t("status.not_registered", lang))
            return

        subs = sub_repo.get_user_subscriptions(user_id)
        user_language = user.language
        num_subs = len(subs)

        # Get user-specific appointment stats
        user_sub_service_ids = [sub["service_id"] for sub in subs]
        all_logs = log_repo.get_all_logs()
        user_appointments = [
            log for log in all_logs if log["service_id"] in user_sub_service_ids
        ]

    start_date, end_date = get_user_date_range(user_id)

    # Get global stats for timing info
    stats = get_stats()
    last_check = stats.get("last_check_time")
    check_interval = get_config().check_interval

    # Calculate time since last check
    if last_check:
        time_since_check = (datetime.now() - last_check).total_seconds()
        if time_since_check < 60:
            last_check_str = t("status.seconds_ago", lang, count=int(time_since_check))
        elif time_since_check < 3600:
            last_check_str = t(
                "status.minutes_ago", lang, count=int(time_since_check / 60)
            )
        else:
            last_check_str = t(
                "status.hours_ago", lang, count=int(time_since_check / 3600)
            )

        # Calculate next check estimate
        next_check_seconds = max(0, check_interval - time_since_check)
        if next_check_seconds < 60:
            next_check_str = t(
                "status.next_in_seconds", lang, count=int(next_check_seconds)
            )
        else:
            next_check_str = t(
                "status.next_in_minutes", lang, count=int(next_check_seconds / 60)
            )
    else:
        last_check_str = t("status.last_check_never", lang)
        next_check_str = t("status.next_check_soon", lang)

    # User-specific appointment stats
    user_appointments_count = len(user_appointments)
    if user_appointments and user_appointments_count > 0:
        latest_appointment = user_appointments[0]  # Assuming sorted by found_at desc
        latest_time = latest_appointment.get("found_at", "")
        if latest_time:
            try:
                latest_dt = datetime.fromisoformat(latest_time)
                days_ago = (datetime.now() - latest_dt).days
                if days_ago == 0:
                    latest_str = t("status.found_today", lang)
                elif days_ago == 1:
                    latest_str = t("status.found_yesterday", lang)
                else:
                    latest_str = t("status.found_days_ago", lang, count=days_ago)
            except (ValueError, TypeError):
                latest_str = t("status.found_recently", lang)
        else:
            latest_str = t("status.found_recently", lang)
        stats_line = t(
            "status.appointments_found",
            lang,
            found=user_appointments_count,
            latest=latest_str,
        )
    else:
        stats_line = t("status.appointments_found_none", lang)

    message = t(
        "status.message",
        lang,
        user_id=user_id,
        num_subs=num_subs,
        start_date=start_date,
        end_date=end_date,
        language=user_language,
        last_check=last_check_str,
        next_check=next_check_str,
        check_interval=t("status.interval_seconds", lang, count=check_interval),
        stats_line=stats_line,
    )

    keyboard = [
        [
            InlineKeyboardButton(
                t("common.btn_main_menu", lang), callback_data="main_menu"
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message, reply_markup=reply_markup, parse_mode="HTML"
    )
