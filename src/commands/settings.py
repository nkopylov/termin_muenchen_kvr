# ABOUTME: Settings screen: language, saved booking details and deleting all data.
# ABOUTME: Entry points for /settings and every "s1:" button.

import html
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes

from src.commands import stop
from src.database import get_session
from src.handlers import text_input
from src.i18n import t
from src.i18n.user_language import get_stored_language, get_user_language
from src.repositories import UserRepository, WatchRepository
from src.services.analytics_service import track_event
from src.ui import callbacks as cb
from src.ui.background import run_for_user
from src.ui.screens import forget_nav_message, show_screen
from src.ui.telegram_safe import safe_answer, safe_delete, safe_edit_text, safe_send
from src.watches import when

logger = logging.getLogger(__name__)


def build_settings_screen(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    with get_session() as session:
        contact = UserRepository(session).get_booking_contact(user_id)
    contact_text = (
        ", ".join(html.escape(part) for part in contact)
        if contact
        else t("settings.contact_none", lang)
    )
    rows = [
        [InlineKeyboardButton(t("language.btn_menu", lang), callback_data="language")]
    ]
    if contact:
        rows.append(
            [
                InlineKeyboardButton(
                    t("settings.btn_forget", lang), callback_data=cb.settings_forget()
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                t("settings.btn_delete", lang), callback_data=cb.settings_delete()
            )
        ]
    )
    text = t(
        "settings.text",
        lang,
        language=t(f"language.btn_{lang}", lang),
        contact=contact_text,
    )
    return text, InlineKeyboardMarkup(rows)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    text, markup = build_settings_screen(user_id, lang)
    await show_screen(update, context, text, markup)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/settings and the reply keyboard's Settings button"""
    text_input.clear_pending_input(context)
    user_id = update.effective_user.id
    if get_stored_language(user_id) is None:
        lang = get_user_language(user_id, context)
        await safe_send(
            context.bot, update.effective_chat.id, t("start.not_registered", lang)
        )
        return
    await show_settings(update, context)


async def _delete_everything(
    update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str
) -> None:
    bot = context.bot
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message = update.callback_query.message
    with get_session() as session:
        user = UserRepository(session).get_user(user_id)
        registered_at = None if user is None else user.subscribed_at
        open_watches = WatchRepository(session).count_open(user_id)

    if user is not None:
        await stop.delete_user_data(bot, user_id, lang)
        context.user_data.clear()
    if message is not None:
        await safe_delete(bot, chat_id, message.message_id)
    if user is None:
        return

    await safe_send(bot, chat_id, t("stop.done", lang), ReplyKeyboardRemove())
    days = (when.utcnow() - registered_at).days if registered_at else 0
    await track_event(
        "user_stopped",
        user_id=user_id,
        days_since_registration=days,
        watches_at_stop=open_watches,
    )


async def _keep_data(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """No on the delete confirmation: back to Settings, or a plain note after /stop"""
    message = update.callback_query.message
    pressed = None if message is None else message.message_id
    if pressed is None or context.user_data.get(stop.STOP_CONFIRM_KEY) != pressed:
        await show_settings(update, context)
        return
    context.user_data.pop(stop.STOP_CONFIRM_KEY, None)
    await safe_edit_text(
        context.bot, update.effective_chat.id, pressed, t("stop.kept", lang)
    )
    forget_nav_message(update.effective_user.id, pressed)


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every "s1:" button"""
    query = update.callback_query
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    text_input.clear_pending_input(context)
    parsed = cb.parse(query.data)
    action = "home" if parsed is None else parsed.action

    if action == "forget":
        with get_session() as session:
            UserRepository(session).clear_booking_contact(user_id)
        await safe_answer(query, t("settings.forgotten", lang))
        await show_settings(update, context)
        return

    await safe_answer(query)
    if action == "del":
        text, markup = stop.build_delete_confirm(lang)
        await show_screen(update, context, text, markup)
    elif action == "dely":
        run_for_user(
            context, update, user_id, _delete_everything(update, context, lang)
        )
    elif action == "deln":
        await _keep_data(update, context, lang)
    else:
        await show_settings(update, context)
