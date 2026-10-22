# ABOUTME: Runs first on every private update of a registered user (handler group -3).
# ABOUTME: Resumes watches paused because the bot was blocked and delivers the reply keyboard once.

import logging

from telegram import Chat, Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.i18n import is_language_chosen, t
from src.repositories import UserRepository, WatchRepository
from src.ui.commands_menu import set_chat_commands
from src.ui.keyboard import main_keyboard
from src.ui.telegram_safe import safe_send

logger = logging.getLogger(__name__)

UI_COMMANDS_SET = 1
UI_KEYBOARD_DELIVERED = 2


def _delivers_keyboard_itself(update: Update) -> bool:
    """/start and the language choice send the keyboard with their own messages."""
    query = update.callback_query
    if query is not None:
        return (query.data or "").startswith("lang:")
    text = update.message.text if update.message is not None else None
    if not text or not text.startswith("/"):
        return False
    return text.split()[0][1:].split("@")[0].lower() == "start"


async def on_presence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or chat.type != Chat.PRIVATE:
        return
    if update.message is None and update.callback_query is None:
        return

    with get_session() as session:
        record = UserRepository(session).get_user(user.id)
        if record is None or not is_language_chosen(record.language):
            return
        lang = record.language
        ui_version = record.ui_version
        resumed = WatchRepository(session).resume_blocked(user.id)

    if resumed:
        logger.info(f"Resumed {resumed} watch(es) of user {user.id} after a block")
        await safe_send(context.bot, chat.id, t("watch.resumed", lang, count=resumed))

    if ui_version >= UI_KEYBOARD_DELIVERED or _delivers_keyboard_itself(update):
        return
    if ui_version < UI_COMMANDS_SET:
        await set_chat_commands(context.bot, chat.id, lang)
    await safe_send(
        context.bot, chat.id, t("keyboard.upgrade", lang), main_keyboard(lang)
    )
    with get_session() as session:
        UserRepository(session).set_ui_version(user.id, UI_KEYBOARD_DELIVERED)
