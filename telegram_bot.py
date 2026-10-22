"""
Munich Appointment Bot - Main Entry Point
Minimal bot setup that wires together all commands and handlers.
"""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, TypeHandler

from src.config import get_config
from src.database import init_database

# Import commands
from src.commands.start import start_command
from src.commands.stop import stop_command
from src.commands.menu import menu_command
from src.commands.subscribe import subscribe_command
from src.commands.myservices import myservices_command
from src.commands.setdates import setdates_command
from src.commands.status import status_command
from src.commands.stats import stats_command
from src.commands.help import help_command
from src.commands.booking import booking_conversation
from src.commands.language import (
    language_choice_callback,
    language_command,
    language_gate,
    language_menu_callback,
    set_default_commands,
)

# Import handlers
from src.handlers.buttons import button_callback

# Import services
from src.services.appointment_checker import check_and_notify, set_bot_start_time
from src.services.analytics_service import cleanup_analytics

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Post-initialization callback - set bot commands and start time"""
    set_bot_start_time()

    # Set bot commands for menu
    await set_default_commands(application.bot)
    logger.info("Bot commands set")

    # Start background task for checking appointments
    application.create_task(check_and_notify(application))
    logger.info("Background appointment checker started")


async def post_shutdown(application: Application) -> None:
    """Post-shutdown callback - cleanup analytics HTTP client"""
    logger.info("Shutting down bot...")
    await cleanup_analytics()
    logger.info("Bot shutdown complete")


def register_handlers(application: Application) -> None:
    """Register all update handlers in dispatch order"""
    # Runs before every other handler; stops users without a language until they choose
    application.add_handler(TypeHandler(Update, language_gate), group=-1)

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("myservices", myservices_command))
    application.add_handler(CommandHandler("setdates", setdates_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("language", language_command))

    # Register booking conversation handler
    application.add_handler(booking_conversation)

    # Language callbacks must precede the catch-all button handler
    application.add_handler(
        CallbackQueryHandler(language_choice_callback, pattern="^lang:")
    )
    application.add_handler(
        CallbackQueryHandler(language_menu_callback, pattern="^language$")
    )

    # Register button callback handler
    application.add_handler(CallbackQueryHandler(button_callback))


def main() -> None:
    """Start the bot"""
    config = get_config()

    # Initialize database
    logger.info("Initializing database...")
    init_database()

    # Create application
    application = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    register_handlers(application)

    # Start bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
