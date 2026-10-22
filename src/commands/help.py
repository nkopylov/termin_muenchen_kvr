# ABOUTME: /help and the reply keyboard's Help button: how the bot works and its commands.
# ABOUTME: Shown as a navigation screen with shortcuts to Find and My watches.

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.handlers import text_input
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.ui import callbacks as cb
from src.ui.screens import show_screen


def build_help_screen(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("keyboard.find", lang), callback_data=cb.find_home()
                ),
                InlineKeyboardButton(
                    t("keyboard.watches", lang), callback_data=cb.watches_list()
                ),
            ]
        ]
    )
    return t("help.text", lang, find=t("keyboard.find", lang)), markup


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text_input.clear_pending_input(context)
    lang = get_user_language(update.effective_user.id, context)
    text, markup = build_help_screen(lang)
    await show_screen(update, context, text, markup)
