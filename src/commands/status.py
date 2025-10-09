"""
/status command - Show user's current status and settings
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository, SubscriptionRepository
from src.services.appointment_checker import get_user_date_range
from src.config import get_config

logger = logging.getLogger(__name__)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot status"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        user = user_repo.get_user(user_id)
        if not user:
            await update.message.reply_text(
                "❌ You are not registered.\n\nUse /start to register."
            )
            return

        subs = sub_repo.get_user_subscriptions(user_id)
        user_language = user.language
        num_subs = len(subs)

    start_date, end_date = get_user_date_range(user_id)

    message = (
        "📊 <b>Your Status</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"📋 Subscriptions: <b>{num_subs}</b>\n"
        f"📅 Date Range: {start_date} to {end_date}\n"
        f"🌐 Language: {user_language}\n\n"
        f"⏱ Check Interval: {get_config().check_interval} seconds"
    )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="HTML")
