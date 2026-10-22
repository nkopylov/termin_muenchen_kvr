# ABOUTME: The persistent reply keyboard (Find, My watches, Settings, Help) and matching of its labels.
# ABOUTME: Labels of every language match, so keyboards keep working after a language switch.

from enum import StrEnum

from telegram import KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import filters

from src.i18n import SUPPORTED_LANGUAGES, t


class MenuAction(StrEnum):
    FIND = "find"
    WATCHES = "watches"
    SETTINGS = "settings"
    HELP = "help"


_LABEL_TO_ACTION: dict[str, MenuAction] = {
    t(f"keyboard.{action.value}", lang): action
    for lang in SUPPORTED_LANGUAGES
    for action in MenuAction
}

MENU_FILTER: filters.BaseFilter = filters.Text(list(_LABEL_TO_ACTION))


def main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    def button(action: MenuAction) -> KeyboardButton:
        return KeyboardButton(t(f"keyboard.{action.value}", lang))

    return ReplyKeyboardMarkup(
        [
            [button(MenuAction.FIND), button(MenuAction.WATCHES)],
            [button(MenuAction.SETTINGS), button(MenuAction.HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def menu_action(text: str | None) -> MenuAction | None:
    return _LABEL_TO_ACTION.get((text or "").strip())
