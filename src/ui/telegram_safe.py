# ABOUTME: Telegram send/edit/delete/answer calls that never raise Telegram errors.
# ABOUTME: Each returns an outcome so callers can react to "gone", "blocked" or transient failures.

import logging
from enum import StrEnum

from telegram import CallbackQuery, InlineKeyboardMarkup, Message
from telegram.error import BadRequest, Forbidden, TelegramError

logger = logging.getLogger(__name__)

NOT_MODIFIED_TEXTS = ("message is not modified",)
GONE_TEXTS = (
    "message to edit not found",
    "message can't be edited",
    "message to delete not found",
    "message can't be deleted",
)
EXPIRED_QUERY_TEXTS = ("query is too old", "query id is invalid")


class EditOutcome(StrEnum):
    OK = "ok"
    NOT_MODIFIED = "not_modified"
    GONE = "gone"
    FORBIDDEN = "forbidden"
    FAILED = "failed"


def classify(exc: Exception) -> EditOutcome:
    if isinstance(exc, Forbidden):
        return EditOutcome.FORBIDDEN
    if isinstance(exc, BadRequest):
        message = str(exc).lower()
        if any(text in message for text in NOT_MODIFIED_TEXTS):
            return EditOutcome.NOT_MODIFIED
        if any(text in message for text in GONE_TEXTS):
            return EditOutcome.GONE
    return EditOutcome.FAILED


def _log(
    action: str, chat_id: int, message_id: int | None, exc: TelegramError
) -> EditOutcome:
    outcome = classify(exc)
    level = logging.WARNING if outcome is EditOutcome.FAILED else logging.DEBUG
    logger.log(
        level, f"{action} chat={chat_id} message={message_id}: {outcome} ({exc})"
    )
    return outcome


async def safe_edit_text(
    bot,
    chat_id: int,
    message_id: int,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
) -> EditOutcome:
    """Edit a message's text; without `markup` its inline buttons are removed."""
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode=parse_mode,
            reply_markup=markup,
        )
        return EditOutcome.OK
    except TelegramError as exc:
        return _log("edit", chat_id, message_id, exc)


async def safe_strip_markup(bot, chat_id: int, message_id: int) -> EditOutcome:
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None
        )
        return EditOutcome.OK
    except TelegramError as exc:
        return _log("strip", chat_id, message_id, exc)


async def safe_delete(bot, chat_id: int, message_id: int) -> bool:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except TelegramError as exc:
        _log("delete", chat_id, message_id, exc)
        return False


async def safe_send(
    bot, chat_id: int, text: str, markup=None, silent: bool = False
) -> tuple[Message | None, EditOutcome]:
    """Send an HTML message; `markup` may be inline or a reply keyboard."""
    try:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_notification=silent,
        )
        return message, EditOutcome.OK
    except TelegramError as exc:
        return None, _log("send", chat_id, None, exc)


async def safe_answer(
    query: CallbackQuery | None, text: str | None = None, show_alert: bool = False
) -> bool:
    """Answer a callback query; False when it expired or could not be answered."""
    if query is None:
        return False
    try:
        await query.answer(text=text, show_alert=show_alert)
        return True
    except TelegramError as exc:
        message = str(exc).lower()
        if not any(t in message for t in EXPIRED_QUERY_TEXTS):
            logger.warning(f"Could not answer callback query: {exc}")
        return False
