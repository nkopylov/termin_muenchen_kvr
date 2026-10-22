# ABOUTME: /language command, language picker callbacks and the gate that asks unset users to choose.
# ABOUTME: Also builds the per-language Telegram command list.

import logging

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from src.commands.start import build_welcome
from src.handlers.language_picker import build_language_picker, send_language_picker
from src.i18n import DEFAULT_LANGUAGE, is_language_chosen, t
from src.i18n.user_language import (
    CACHE_KEY,
    get_stored_language,
    set_user_language,
)
from src.services.analytics_service import track_event

logger = logging.getLogger(__name__)

BOT_COMMANDS = (
    "start",
    "menu",
    "subscribe",
    "myservices",
    "setdates",
    "status",
    "help",
    "language",
    "stop",
)
GATE_FREE_COMMANDS = ("start", "language", "stop")
GATE_FREE_CALLBACK_PREFIXES = ("lang:", "book_", "time_")
GATE_FREE_CALLBACKS = ("confirm_booking", "cancel_booking")


def bot_commands(lang: str) -> list[BotCommand]:
    return [BotCommand(name, t(f"commands.{name}", lang)) for name in BOT_COMMANDS]


async def set_default_commands(bot) -> None:
    """English for everyone, Russian for clients whose Telegram language is Russian"""
    await bot.set_my_commands(bot_commands(DEFAULT_LANGUAGE))
    await bot.set_my_commands(bot_commands("ru"), language_code="ru")


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /language: show the picker"""
    await send_language_picker(update, context)


async def language_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle the main menu's Language button: replace the menu with the picker"""
    query = update.callback_query
    await query.answer()
    text, markup = build_language_picker(update.effective_user.language_code)
    await query.edit_message_text(text, reply_markup=markup)


async def language_choice_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle a "lang:<code>" button: store the choice and reply in that language"""
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    if not is_language_chosen(lang):
        return

    user = update.effective_user
    previous = get_stored_language(user.id)
    if previous is None:
        await query.edit_message_text(t("menu.not_registered", lang))
        return

    set_user_language(user.id, lang, context)
    try:
        await context.bot.set_my_commands(
            bot_commands(lang), scope=BotCommandScopeChat(update.effective_chat.id)
        )
    except TelegramError as e:
        logger.warning(f"Could not set chat commands for user {user.id}: {e}")
    await track_event("language_selected", user_id=user.id, language=lang)

    if is_language_chosen(previous):
        text = t("language.changed", lang)
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t("common.btn_main_menu", lang), callback_data="main_menu"
                    )
                ]
            ]
        )
    else:
        text, markup = build_welcome(lang)
    await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")


def _passes_gate(update: Update) -> bool:
    # Booking buttons and typed booking answers are time-critical; /stop must always work
    query = update.callback_query
    if query is not None:
        data = query.data or ""
        return (
            data == "language"
            or data.startswith(GATE_FREE_CALLBACK_PREFIXES)
            or data in GATE_FREE_CALLBACKS
        )

    message = update.message
    if message is None or not message.text or not message.text.startswith("/"):
        return True
    command = message.text.split()[0][1:].split("@")[0].lower()
    return command in GATE_FREE_COMMANDS


async def language_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask registered users without a language to choose one before anything else"""
    user = update.effective_user
    if user is None or CACHE_KEY in context.user_data or _passes_gate(update):
        return

    stored = get_stored_language(user.id)
    if stored is None:
        return
    if is_language_chosen(stored):
        context.user_data[CACHE_KEY] = stored
        return

    if update.callback_query is not None:
        await update.callback_query.answer()
    await send_language_picker(update, context)
    raise ApplicationHandlerStop
