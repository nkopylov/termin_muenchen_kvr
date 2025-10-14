"""
/start command - Register new users and show welcome message
"""

import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository
from src.services.analytics_service import track_event

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

            # Track new user registration
            await track_event(
                "user_registered",
                user_id=user_id,
                username=username or "anonymous"
            )
        else:
            # Existing user - check if re-engaged
            if user.subscribed_at:
                days_inactive = (datetime.utcnow() - user.subscribed_at).days
                if days_inactive > 30:
                    await track_event(
                        "user_reengaged",
                        user_id=user_id,
                        days_inactive=days_inactive
                    )

    # Show welcome message
    welcome_msg = (
        "👋 <b>Welcome to Munich Appointment Bot!</b>\n\n"
        "🎯 <b>What I do:</b>\n"
        "I monitor the Munich city appointment system (Ausländerbehörde, "
        "Bürgeramt, KVR) 24/7 and notify you instantly when appointments become available.\n\n"
        "🚀 <b>How it works:</b>\n"
        "1️⃣ <b>Subscribe</b> to services you need (e.g., visa, passport, residence permit)\n"
        "2️⃣ <b>Set your date range</b> - when you're available for appointments\n"
        "3️⃣ <b>Get notified</b> immediately when slots open up\n"
        "4️⃣ <b>Book instantly</b> through the bot or on the website\n\n"
        "⚡ <b>Getting Started:</b>\n"
        "• Set your date range: /setdates\n"
        "• Subscribe to services: /subscribe\n"
        "• View main menu: /menu\n"
        "• Get help: /help\n\n"
        "💡 <b>Tip:</b> Set a realistic date range (e.g., next 3 months) for better results!"
    )

    # Add menu button
    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_msg, reply_markup=reply_markup, parse_mode="HTML"
    )
