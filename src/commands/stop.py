# ABOUTME: /stop asks to delete all of the user's data; delete_user_data performs the deletion.
# ABOUTME: Deletion first finalizes the user's messages that still carry buttons, then removes every row.

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.handlers import text_input
from src.i18n import t
from src.i18n.user_language import get_stored_language, get_user_language
from src.repositories import (
    BookingSessionRepository,
    PendingRetireRepository,
    UserRepository,
    WatchRepository,
)
from src.ui import callbacks as cb
from src.ui.screens import retire_nav_message, show_screen
from src.ui.telegram_safe import safe_edit_text, safe_send
from src.watches.alert_ops import alert_lock, close_live_alert
from src.watches.alert_view import FinalState

logger = logging.getLogger(__name__)

# user_data key: id of the confirmation sent by /stop, so "No" there answers in place
STOP_CONFIRM_KEY = "stop_confirm_msg"


def build_delete_confirm(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("stop.btn_yes", lang), callback_data=cb.settings_delete_yes()
                ),
                InlineKeyboardButton(
                    t("stop.btn_no", lang), callback_data=cb.settings_delete_no()
                ),
            ]
        ]
    )
    return t("stop.confirm", lang), markup


async def delete_user_data(bot, user_id: int, lang: str) -> None:
    """Finalize live messages and delete every row of the user"""
    with get_session() as session:
        records = WatchRepository(session).list_for_user(user_id, None)
        booking = BookingSessionRepository(session).get_session(user_id)
        booking_message = None if booking is None else booking.message_id

    for rec in records:
        async with alert_lock(rec.id):
            # Ended first, so a check cycle reaching this watch before the cascade sends nothing
            if rec.is_open:
                with get_session() as session:
                    WatchRepository(session).set_status(
                        rec.id, "ended", end_reason="stopped"
                    )
            await close_live_alert(bot, rec.id, FinalState.STOPPED, lang, by_user=True)
    if booking_message is not None:
        await safe_edit_text(
            bot, user_id, booking_message, t("booking.session_cleared", lang)
        )

    with get_session() as session:
        queued = PendingRetireRepository(session).list_for_user(user_id)
    for item in queued:
        await safe_edit_text(bot, item.chat_id, item.message_id, item.text)
    await retire_nav_message(bot, user_id)

    with get_session() as session:
        UserRepository(session).delete_user_cascade(user_id)
    logger.info(f"Deleted all data of user {user_id}")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop: ask before deleting everything"""
    text_input.clear_pending_input(context)
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    if get_stored_language(user_id) is None:
        await safe_send(
            context.bot, update.effective_chat.id, t("start.not_registered", lang)
        )
        return

    text, markup = build_delete_confirm(lang)
    message = await show_screen(update, context, text, markup)
    if message is not None:
        context.user_data[STOP_CONFIRM_KEY] = message.message_id
