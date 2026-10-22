"""
Munich Appointment Bot - Main Entry Point
Minimal bot setup that wires together all commands and handlers.
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from src import services_manager
from src.commands.booking import (
    booking_conversation,
    booking_orphan_callback,
    end_all_booking_sessions,
)
from src.commands.find import find_callback, find_command
from src.commands.help import help_command
from src.commands.language import (
    language_choice_callback,
    language_command,
    language_gate,
    language_menu_callback,
)
from src.commands.settings import settings_callback, settings_command

# Import commands
from src.commands.start import start_command
from src.commands.stats import stats_command
from src.commands.stop import stop_command
from src.commands.watches import watches_callback, watches_command
from src.config import get_config
from src.database import init_database

# Import handlers
from src.handlers.errors import on_error
from src.handlers.interaction_tracker import record_interaction
from src.handlers.legacy_callbacks import legacy_callback
from src.handlers.menu_keyboard import menu_text
from src.handlers.presence import on_presence
from src.handlers.text_input import on_text
from src.services.analytics_service import cleanup_analytics
from src.services.announcement import announce_new_ui

# Import services
from src.services.appointment_checker import check_and_notify, set_bot_start_time
from src.ui.callbacks import (
    BOOK_RE,
    FIND_RE,
    LEGACY_BOOKING_RE,
    SETTINGS_RE,
    WATCH_RE,
)
from src.ui.commands_menu import set_default_commands
from src.ui.keyboard import MENU_FILTER

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

PRIVATE = filters.ChatType.PRIVATE

COMMANDS = (
    ("start", start_command),
    ("find", find_command),
    ("watches", watches_command),
    ("settings", settings_command),
    ("help", help_command),
    ("language", language_command),
    ("stop", stop_command),
    ("stats", stats_command),
    # Alias commands, kept so typed commands keep working
    ("menu", find_command),
    ("subscribe", find_command),
    ("myservices", watches_command),
    ("status", watches_command),
    ("setdates", watches_command),
)


async def startup_sequence(application: Application) -> None:
    """Announce the reply-keyboard menu first, so no alert reaches a user before it"""
    await announce_new_ui(application.bot)
    logger.info("Background appointment checker started")
    await check_and_notify(application)


async def post_init(application: Application) -> None:
    """Post-initialization callback - set bot commands and start time"""
    set_bot_start_time()

    # In a thread: every catalog read on the event loop uses this cache
    await asyncio.to_thread(services_manager.refresh_catalog)

    # Set bot commands for menu
    await set_default_commands(application.bot)
    logger.info("Bot commands set")

    # Booking conversations do not survive a restart; their DB sessions must not either
    await end_all_booking_sessions(application.bot)

    application.create_task(startup_sequence(application))


async def post_shutdown(application: Application) -> None:
    """Post-shutdown callback - cleanup analytics HTTP client"""
    logger.info("Shutting down bot...")
    await cleanup_analytics()
    logger.info("Bot shutdown complete")


def register_handlers(application: Application) -> None:
    """Register all update handlers in dispatch order"""
    # Resumes watches paused by a block and delivers the reply keyboard once
    application.add_handler(TypeHandler(Update, on_presence), group=-3)
    # Marks the pressed message as in use; never stops other groups
    application.add_handler(CallbackQueryHandler(record_interaction), group=-2)
    # Stops users without a language until they choose
    application.add_handler(TypeHandler(Update, language_gate), group=-1)

    # Booking conversation is the only handler in group 0
    application.add_handler(booking_conversation, group=0)

    for name, callback in COMMANDS:
        application.add_handler(
            CommandHandler(name, callback, filters=PRIVATE), group=1
        )

    callbacks = (
        (language_choice_callback, "^lang:"),
        (language_menu_callback, "^language$"),
        (find_callback, FIND_RE),
        (watches_callback, WATCH_RE),
        (settings_callback, SETTINGS_RE),
        (booking_orphan_callback, f"{BOOK_RE}|{LEGACY_BOOKING_RE}"),
    )
    for callback, pattern in callbacks:
        application.add_handler(
            CallbackQueryHandler(callback, pattern=pattern), group=1
        )

    # Reply keyboard taps must precede the plain-text search
    application.add_handler(MessageHandler(PRIVATE & MENU_FILTER, menu_text), group=1)
    application.add_handler(
        MessageHandler(PRIVATE & filters.TEXT & ~filters.COMMAND, on_text), group=1
    )

    # Buttons no other handler took
    application.add_handler(CallbackQueryHandler(legacy_callback), group=1)

    application.add_error_handler(on_error)


def build_application(token: str) -> Application:
    return (
        Application.builder()
        .token(token)
        .rate_limiter(AIORateLimiter(max_retries=2))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )


def main() -> None:
    """Start the bot"""
    config = get_config()

    # Initialize database
    logger.info("Initializing database...")
    init_database()

    # Create application
    application = build_application(config.telegram_bot_token)

    register_handlers(application)

    # Start bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
