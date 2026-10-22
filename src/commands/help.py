"""
/help command - Comprehensive help documentation
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.i18n import t
from src.i18n.user_language import get_user_language

logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show comprehensive help information"""
    lang = get_user_language(update.effective_user.id, context)
    help_text = t("help.text", lang)

    keyboard = [
        [
            InlineKeyboardButton(
                t("common.btn_main_menu", lang), callback_data="main_menu"
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        help_text, reply_markup=reply_markup, parse_mode="HTML"
    )
