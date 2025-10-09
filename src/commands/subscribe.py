"""
/subscribe command - Show service category selection for subscriptions
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.services_manager import categorize_services

logger = logging.getLogger(__name__)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show category selection"""
    categories = categorize_services()

    # Create category buttons (2 per row)
    keyboard = []
    cat_items = list(categories.items())

    for i in range(0, len(cat_items), 2):
        row = []
        for j in range(2):
            if i + j < len(cat_items):
                category, services = cat_items[i + j]
                row.append(InlineKeyboardButton(
                    f"{category} ({len(services)})",
                    callback_data=f"cat:{category}"
                ))
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📋 <b>Select a Category:</b>\n\nChoose a service category to see available services.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
