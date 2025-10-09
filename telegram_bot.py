"""
Munich Appointment Bot - Main Entry Point
Minimal bot setup that wires together all commands and handlers.
"""
import logging
import asyncio
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

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
from src.commands.booking import booking_conversation

# Import handlers
from src.handlers.buttons import button_callback

# Import services
from src.services.appointment_checker import check_and_notify, set_bot_start_time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Post-initialization callback - set bot commands and start time"""
    set_bot_start_time()

    # Set bot commands for menu
    commands = [
        BotCommand("start", "Start the bot and register"),
        BotCommand("menu", "Show main menu"),
        BotCommand("subscribe", "Subscribe to services"),
        BotCommand("myservices", "View your subscriptions"),
        BotCommand("setdates", "Set date range filter"),
        BotCommand("status", "Show your status"),
        BotCommand("stats", "Show bot statistics"),
        BotCommand("stop", "Unsubscribe and delete data"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set")

    # Start background task for checking appointments
    application.create_task(check_and_notify(application))
    logger.info("Background appointment checker started")


def main() -> None:
    """Start the bot"""
    config = get_config()

    # Initialize database
    logger.info("Initializing database...")
    init_database()

    # Create application
    application = Application.builder().token(config.telegram_bot_token).post_init(post_init).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("myservices", myservices_command))
    application.add_handler(CommandHandler("setdates", setdates_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stats", stats_command))

    # Register booking conversation handler
    application.add_handler(booking_conversation)

    # Register button callback handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == '__main__':
    main()
