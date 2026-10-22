# ABOUTME: /start registers new users (then asks for a language) and welcomes everyone else.
# ABOUTME: Onboarding sends the reply keyboard, then Find for new users or My watches for watchers.

import logging
from datetime import UTC, datetime

from telegram import Update
from telegram.ext import ContextTypes

from src.commands import find, watches
from src.database import get_session
from src.handlers import text_input
from src.handlers.language_picker import send_language_picker
from src.handlers.presence import UI_KEYBOARD_DELIVERED
from src.i18n import is_language_chosen, t
from src.i18n.user_language import clear_cached_language, get_user_language
from src.repositories import UserRepository, WatchRepository
from src.services.analytics_service import track_event
from src.ui.keyboard import main_keyboard
from src.ui.screens import retire_nav_message
from src.ui.telegram_safe import safe_send
from src.watches import when

logger = logging.getLogger(__name__)


async def register_user(user_id: int, username: str | None) -> None:
    """Create a user with no language chosen yet"""
    with get_session() as session:
        UserRepository(session).create_user(user_id=user_id, username=username)

    # Track new user registration
    await track_event(
        "user_registered", user_id=user_id, username=username or "anonymous"
    )


async def send_onboarding(
    bot, chat_id: int, user_id: int, lang: str, returning: bool
) -> None:
    """Welcome with the reply keyboard, then the Find screen or My watches"""
    key = "start.welcome_back" if returning else "start.welcome"
    welcome, _ = await safe_send(bot, chat_id, t(key, lang), main_keyboard(lang))
    with get_session() as session:
        if welcome is not None:
            UserRepository(session).set_ui_version(user_id, UI_KEYBOARD_DELIVERED)
        open_watches = WatchRepository(session).count_open(user_id)

    if open_watches:
        text, markup = watches.build_watches_screen(user_id, lang, when.utcnow())
    else:
        text, markup = find.build_find_screen(lang)
    await retire_nav_message(bot, user_id)
    screen, _ = await safe_send(bot, chat_id, text, markup)
    if screen is not None:
        with get_session() as session:
            UserRepository(session).set_nav_message_id(user_id, screen.message_id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    text_input.clear_pending_input(context)
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

    await send_onboarding(
        context.bot,
        update.effective_chat.id,
        user_id,
        get_user_language(user_id, context),
        returning=True,
    )
