"""
/subscribe command - Show service category selection for subscriptions
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.i18n import t
from src.i18n.user_language import get_user_language
from src.services_manager import categorize_services

logger = logging.getLogger(__name__)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show category selection"""
    lang = get_user_language(update.effective_user.id, context)
    categories = categorize_services()

    # Create category buttons (2 per row)
    keyboard = []
    cat_items = list(categories.items())

    for i in range(0, len(cat_items), 2):
        row = []
        for j in range(2):
            if i + j < len(cat_items):
                category, services = cat_items[i + j]
                row.append(
                    InlineKeyboardButton(
                        f"{t(f'categories.{category}', lang)} ({len(services)})",
                        callback_data=f"cat:{category}",
                    )
                )
        keyboard.append(row)

    # Add Main Menu button
    keyboard.append(
        [
            InlineKeyboardButton(
                t("common.btn_main_menu", lang), callback_data="main_menu"
            )
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        t("subscribe.select_category", lang),
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
