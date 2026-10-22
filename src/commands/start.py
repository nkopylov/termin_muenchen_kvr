"""
/start command - Register new users and show welcome message
"""

import logging
from datetime import UTC, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.handlers.language_picker import send_language_picker
from src.i18n import is_language_chosen, t
from src.i18n.user_language import clear_cached_language, get_user_language
from src.repositories import UserRepository
from src.services.analytics_service import track_event

logger = logging.getLogger(__name__)


async def register_user(user_id: int, username: str | None) -> None:
    """Create a user with the default date range and no language chosen yet"""
    # New user - create with default date range
    today = datetime.now()
    end_date = today + timedelta(days=180)
    with get_session() as session:
        UserRepository(session).create_user(
            user_id=user_id,
            username=username,
            start_date=today.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

    # Track new user registration
    await track_event(
        "user_registered", user_id=user_id, username=username or "anonymous"
    )


def build_welcome(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    """Welcome text and its Main Menu button in the given language"""
    # Add menu button
    keyboard = [
        [
            InlineKeyboardButton(
                t("common.btn_main_menu", lang), callback_data="main_menu"
            )
        ]
    ]
    return t("start.welcome", lang), InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    with get_session() as session:
        user = UserRepository(session).get_user(user_id)
        stored_language = user.language if user else None
        subscribed_at = user.subscribed_at if user else None

    if stored_language is None:
        clear_cached_language(context)
        await register_user(user_id, username)
        await send_language_picker(update, context)
        return

    # Existing user - check if re-engaged
    if subscribed_at:
        days_inactive = (datetime.now(UTC).replace(tzinfo=None) - subscribed_at).days
        if days_inactive > 30:
            await track_event(
                "user_reengaged", user_id=user_id, days_inactive=days_inactive
            )

    if not is_language_chosen(stored_language):
        await send_language_picker(update, context)
        return

    # Show welcome message
    welcome_msg, reply_markup = build_welcome(get_user_language(user_id, context))
    await update.message.reply_text(
        welcome_msg, reply_markup=reply_markup, parse_mode="HTML"
    )
