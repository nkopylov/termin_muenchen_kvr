"""
/stats command - Show bot statistics (admin only)
"""

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.config import get_config
from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import SubscriptionRepository, UserRepository
from src.services.appointment_checker import get_stats

logger = logging.getLogger(__name__)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics (admin only)"""
    config = get_config()
    user_id = update.effective_user.id

    # Check if user is admin
    if not config.admin_telegram_id or user_id != config.admin_telegram_id:
        lang = get_user_language(user_id, context)
        await update.message.reply_text(t("common.admin_only", lang))
        logger.warning(f"User {user_id} attempted to access /stats command")
        return

    stats = get_stats()

    uptime = "N/A"
    if stats["bot_start_time"]:
        uptime_seconds = (datetime.now() - stats["bot_start_time"]).total_seconds()
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        uptime = f"{hours}h {minutes}m"

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        total_users = len(user_repo.get_all_users())
        service_subs = sub_repo.get_all_service_subscriptions()
        total_services = len(service_subs)

    success_rate = 0
    if stats["total_checks"] > 0:
        success_rate = (stats["successful_checks"] / stats["total_checks"]) * 100

    message = (
        "📈 <b>Bot Statistics</b>\n\n"
        f"⏱ Uptime: {uptime}\n"
        f"👥 Users: {total_users}\n"
        f"📋 Unique Service Subscriptions: {total_services}\n\n"
        f"🔍 Total checks: {stats['total_checks']}\n"
        f"✅ Successful: {stats['successful_checks']}\n"
        f"❌ Failed: {stats['failed_checks']}\n"
        f"📊 Success rate: {success_rate:.1f}%\n\n"
        f"🎯 Appointments found: {stats['appointments_found_count']}\n"
        f"🚀 Bookings started: {stats['bookings_started']}\n"
        f"✅ Bookings completed: {stats['bookings_completed']}\n"
    )

    if stats["last_check_time"]:
        message += f"\n⏰ Last check: {stats['last_check_time'].strftime('%H:%M:%S')}"
    if stats["last_success_time"]:
        message += (
            f"\n✅ Last success: {stats['last_success_time'].strftime('%H:%M:%S')}"
        )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message, reply_markup=reply_markup, parse_mode="HTML"
    )
