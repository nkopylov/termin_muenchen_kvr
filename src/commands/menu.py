"""
/menu command - Show main menu with action buttons
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import UserRepository

logger = logging.getLogger(__name__)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with action buttons"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)

    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if not user:
            # Not registered, redirect to /start
            await update.message.reply_text(
                t("menu.not_registered", lang), parse_mode="HTML"
            )
            return

    # Build menu message
    menu_text = t("menu.title", lang)

    # Build keyboard with main actions
    keyboard = [
        [
            InlineKeyboardButton(
                t("menu.btn_subscribe", lang), callback_data="categories"
            )
        ],
        [
            InlineKeyboardButton(
                t("menu.btn_myservices", lang), callback_data="myservices"
            )
        ],
        [InlineKeyboardButton(t("menu.btn_setdates", lang), callback_data="setdates")],
        [InlineKeyboardButton(t("menu.btn_status", lang), callback_data="status")],
        [
            InlineKeyboardButton(
                t("language.btn_menu", lang),
                callback_data="language",
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        menu_text, reply_markup=reply_markup, parse_mode="HTML"
    )
