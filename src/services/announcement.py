# ABOUTME: One-time announcement of the reply-keyboard menu to existing users at startup.
# ABOUTME: Sets their command list and sends the reply keyboard (or, without a language, the picker)
# ABOUTME: to users with open watches.

import logging

from src.database import get_session
from src.handlers.language_picker import build_language_picker
from src.handlers.presence import UI_COMMANDS_SET, UI_KEYBOARD_DELIVERED
from src.i18n import is_language_chosen, t
from src.repositories import UserRepository, WatchRepository
from src.ui.commands_menu import set_chat_commands
from src.ui.keyboard import main_keyboard
from src.ui.screens import send_screen
from src.ui.telegram_safe import EditOutcome, safe_send

logger = logging.getLogger(__name__)


def _pending_users() -> list[tuple[int, str, int]]:
    """(user_id, language, open watches) of users with a language and the old command list"""
    with get_session() as session:
        watches = WatchRepository(session)
        return [
            (user.user_id, user.language, watches.count_open(user.user_id))
            for user in UserRepository(session).get_all_users()
            if is_language_chosen(user.language) and user.ui_version < UI_COMMANDS_SET
        ]


def _watchers_without_language() -> list[int]:
    """Users with open watches whose language was reset (migration v1) and not yet asked"""
    with get_session() as session:
        watches = WatchRepository(session)
        return [
            user.user_id
            for user in UserRepository(session).get_all_users()
            if not is_language_chosen(user.language)
            and user.ui_version < UI_COMMANDS_SET
            and watches.count_open(user.user_id)
        ]


def _set_ui_version(user_id: int, version: int) -> None:
    with get_session() as session:
        UserRepository(session).set_ui_version(user_id, version)


async def announce_new_ui(bot) -> int:
    """Returns how many users were announced to."""
    announced = 0
    for user_id, lang, open_watches in _pending_users():
        await set_chat_commands(bot, user_id, lang)
        if not open_watches:
            _set_ui_version(user_id, UI_COMMANDS_SET)
            continue

        text = t("start.announce", lang, watches=t("keyboard.watches", lang))
        message, outcome = await safe_send(bot, user_id, text, main_keyboard(lang))
        if message is not None:
            _set_ui_version(user_id, UI_KEYBOARD_DELIVERED)
            announced += 1
        elif outcome is EditOutcome.FORBIDDEN:
            _set_ui_version(user_id, UI_KEYBOARD_DELIVERED)
            with get_session() as session:
                WatchRepository(session).pause_all_for_user(user_id, reason="blocked")
    logger.info(f"Announced the new menu to {announced} user(s)")
    await _ask_for_language(bot)
    return announced


async def _ask_for_language(bot) -> None:
    """Their alerts keep coming, so they get the picker now; choosing a language then
    brings the announcement (start.send_onboarding)"""
    asked = 0
    for user_id in _watchers_without_language():
        text, markup = build_language_picker(None)
        message, outcome = await send_screen(bot, user_id, user_id, text, markup)
        if message is not None:
            _set_ui_version(user_id, UI_COMMANDS_SET)
            asked += 1
        elif outcome is EditOutcome.FORBIDDEN:
            _set_ui_version(user_id, UI_KEYBOARD_DELIVERED)
            with get_session() as session:
                WatchRepository(session).pause_all_for_user(user_id, reason="blocked")
    logger.info(f"Asked {asked} watcher(s) without a language to choose one")
