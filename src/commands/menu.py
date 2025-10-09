"""
/menu command - Show main menu with action buttons
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository

logger = logging.getLogger(__name__)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with action buttons"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if not user:
            # Not registered, redirect to /start
            await update.message.reply_text(
                "👋 Welcome! Please use /start to register first.", parse_mode="HTML"
            )
            return

    # Build menu message
    menu_text = "🏠 <b>Main Menu</b>\n\nChoose an action:"

    # Build keyboard with main actions
    keyboard = [
        [InlineKeyboardButton("📋 Subscribe to Services", callback_data="categories")],
        [InlineKeyboardButton("📊 My Subscriptions", callback_data="myservices")],
        [InlineKeyboardButton("📅 Set Date Range", callback_data="setdates")],
        [InlineKeyboardButton("ℹ️ Subscription Status", callback_data="status")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        menu_text, reply_markup=reply_markup, parse_mode="HTML"
    )
