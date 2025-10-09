"""
/start command - Register new users and show welcome message
"""

import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if not user:
            # New user - create with default date range
            today = datetime.now()
            end_date = today + timedelta(days=180)
            user_repo.create_user(
                user_id=user_id,
                username=username,
                language="en",
                start_date=today.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )

    # Show welcome message
    welcome_msg = (
        "👋 <b>Welcome to Munich Appointment Bot!</b>\n\n"
        "I'll help you find available appointments at Munich city offices.\n\n"
        "<b>Quick Start:</b>\n"
        "• Use /subscribe to choose services\n"
        "• Use /menu to access all features\n"
        "• Use /setdates to set your preferred date range\n\n"
        "I'll notify you immediately when appointments become available!"
    )

    # Add menu button
    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_msg, reply_markup=reply_markup, parse_mode="HTML"
    )
