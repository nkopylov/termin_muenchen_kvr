# ABOUTME: Navigation screens edited in place: one current nav message per user (users.nav_message_id).
# ABOUTME: A button press edits its own message; a typed command sends a new one and strips the old.

from telegram import Message, Update
from telegram.error import TelegramError

from src.database import get_session
from src.repositories import UserRepository
from src.ui.telegram_safe import EditOutcome, classify, safe_send, safe_strip_markup


def _pointer(user_id: int) -> int | None:
    with get_session() as session:
        return UserRepository(session).get_nav_message_id(user_id)


def _set_pointer(user_id: int, message_id: int | None) -> None:
    with get_session() as session:
        UserRepository(session).set_nav_message_id(user_id, message_id)


async def show_screen(
    update: Update, context, text: str, markup, parse_mode: str = "HTML"
) -> Message | None:
    """Show a nav screen; returns its message, or None if Telegram refused to show it."""
    bot = context.bot
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    stored = _pointer(user_id)

    query = update.callback_query
    if query is not None and query.message is not None:
        pressed = query.message.message_id
        if stored is not None and stored != pressed:
            await safe_strip_markup(bot, chat_id, stored)
        try:
            edited = await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=pressed,
                parse_mode=parse_mode,
                reply_markup=markup,
            )
            _set_pointer(user_id, pressed)
            return edited if isinstance(edited, Message) else query.message
        except TelegramError as exc:
            outcome = classify(exc)
            if outcome is EditOutcome.NOT_MODIFIED:
                _set_pointer(user_id, pressed)
                return query.message
            if outcome is not EditOutcome.GONE:
                return None
        stored = pressed

    message, _ = await safe_send(bot, chat_id, text, markup)
    if message is None:
        return None
    if stored is not None and stored != message.message_id:
        await safe_strip_markup(bot, chat_id, stored)
    _set_pointer(user_id, message.message_id)
    return message


async def send_screen(
    bot, user_id: int, chat_id: int, text: str, markup
) -> tuple[Message | None, EditOutcome]:
    """Send a nav screen as a new message; the previous nav message loses its buttons."""
    stored = _pointer(user_id)
    message, outcome = await safe_send(bot, chat_id, text, markup)
    if message is None:
        return None, outcome
    if stored is not None and stored != message.message_id:
        await safe_strip_markup(bot, chat_id, stored)
    _set_pointer(user_id, message.message_id)
    return message, outcome


def forget_nav_message(user_id: int, message_id: int | None = None) -> None:
    """Clear the pointer if it is `message_id` (or unconditionally when None)."""
    with get_session() as session:
        users = UserRepository(session)
        if message_id is None or users.get_nav_message_id(user_id) == message_id:
            users.set_nav_message_id(user_id, None)


async def retire_nav_message(bot, user_id: int) -> None:
    """Remove the buttons of the current nav message and forget it."""
    stored = _pointer(user_id)
    if stored is None:
        return
    await safe_strip_markup(bot, user_id, stored)
    _set_pointer(user_id, None)
