# ABOUTME: /language command, language picker callbacks and the gate that asks unset users to choose.
# ABOUTME: The first choice runs onboarding; a later one shows Settings in the new language.

import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from src.commands.settings import show_settings
from src.commands.start import send_onboarding
from src.database import get_session
from src.handlers import text_input
from src.handlers.language_picker import build_language_picker, send_language_picker
from src.handlers.presence import UI_KEYBOARD_DELIVERED
from src.i18n import is_language_chosen, t
from src.i18n.user_language import (
    CACHE_KEY,
    get_stored_language,
    set_user_language,
)
from src.repositories import UserRepository
from src.services.analytics_service import track_event
from src.ui.commands_menu import (  # noqa: F401  (re-exported for callers of this module)
    BOT_COMMANDS,
    bot_commands,
    set_chat_commands,
    set_default_commands,
)
from src.ui.keyboard import main_keyboard
from src.ui.screens import show_screen
from src.ui.telegram_safe import safe_answer, safe_delete, safe_edit_text, safe_send

logger = logging.getLogger(__name__)

GATE_FREE_COMMANDS = ("start", "language", "stop")
GATE_FREE_CALLBACK_PREFIXES = ("lang:", "book_", "time_", "b1:", "s1:del")
GATE_FREE_CALLBACKS = ("confirm_booking", "cancel_booking")


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /language: show the picker (as the nav screen once a language is chosen)"""
    text_input.clear_pending_input(context)
    if not is_language_chosen(get_stored_language(update.effective_user.id)):
        await send_language_picker(update, context)
        return
    text, markup = build_language_picker(update.effective_user.language_code)
    await show_screen(update, context, text, markup, parse_mode=None)


async def language_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle the Settings screen's Language button: replace the screen with the picker"""
    query = update.callback_query
    await safe_answer(query)
    text, markup = build_language_picker(update.effective_user.language_code)
    await safe_edit_text(
        context.bot,
        update.effective_chat.id,
        query.message.message_id,
        text,
        markup,
        parse_mode=None,
    )


async def _language_changed(
    update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str
) -> None:
    """The picker becomes Settings in the new language; a new message brings the keyboard"""
    await show_settings(update, context)
    message, _ = await safe_send(
        context.bot,
        update.effective_chat.id,
        t("language.changed", lang),
        main_keyboard(lang),
    )
    if message is not None:
        with get_session() as session:
            UserRepository(session).set_ui_version(
                update.effective_user.id, UI_KEYBOARD_DELIVERED
            )


async def language_choice_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle a "lang:<code>" button: store the choice and reply in that language"""
    query = update.callback_query
    await safe_answer(query)
    lang = query.data.split(":", 1)[1]
    if not is_language_chosen(lang):
        return

    user = update.effective_user
    chat_id = update.effective_chat.id
    pressed = query.message.message_id if query.message else None
    previous = get_stored_language(user.id)
    if previous is None:
        if pressed is not None:
            await safe_edit_text(
                context.bot, chat_id, pressed, t("start.not_registered", lang)
            )
        return

    set_user_language(user.id, lang, context)
    await set_chat_commands(context.bot, chat_id, lang)
    await track_event("language_selected", user_id=user.id, language=lang)

    if is_language_chosen(previous):
        await _language_changed(update, context, lang)
        return
    if pressed is not None:
        await safe_delete(context.bot, chat_id, pressed)
    await send_onboarding(context.bot, chat_id, user.id, lang, returning=False)


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
