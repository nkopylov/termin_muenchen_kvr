"""
/status command - Show user's current status and settings
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import (
    UserRepository,
    SubscriptionRepository,
    AppointmentLogRepository,
)
from src.services.appointment_checker import get_user_date_range, get_stats
from src.config import get_config
from datetime import datetime

logger = logging.getLogger(__name__)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot status"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        log_repo = AppointmentLogRepository(session)

        user = user_repo.get_user(user_id)
        if not user:
            await update.message.reply_text(
                "❌ You are not registered.\n\nUse /start to register."
            )
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
            last_check_str = f"{int(time_since_check)} seconds ago"
        elif time_since_check < 3600:
            last_check_str = f"{int(time_since_check / 60)} minutes ago"
        else:
            last_check_str = f"{int(time_since_check / 3600)} hours ago"

        # Calculate next check estimate
        next_check_seconds = max(0, check_interval - time_since_check)
        if next_check_seconds < 60:
            next_check_str = f"~{int(next_check_seconds)} seconds"
        else:
            next_check_str = f"~{int(next_check_seconds / 60)} minutes"
    else:
        last_check_str = "Never"
        next_check_str = "Soon"

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
                    latest_str = "today"
                elif days_ago == 1:
                    latest_str = "yesterday"
                else:
                    latest_str = f"{days_ago} days ago"
            except (ValueError, TypeError):
                latest_str = "recently"
        else:
            latest_str = "recently"
        stats_line = (
            f"\n🎯 Appointments found: {user_appointments_count} (last: {latest_str})"
        )
    else:
        stats_line = "\n🎯 Appointments found: 0"

    message = (
        "📊 <b>Your Status</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"📋 Subscriptions: <b>{num_subs}</b>\n"
        f"📅 Date Range: {start_date} to {end_date}\n"
        f"🌐 Language: {user_language}\n\n"
        f"🔍 Last checked: {last_check_str}\n"
        f"⏱ Next check in: {next_check_str}\n"
        f"⚙️ Check interval: {check_interval} seconds"
        f"{stats_line}"
    )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message, reply_markup=reply_markup, parse_mode="HTML"
    )
