# ABOUTME: Taps on the persistent reply keyboard (Find, My watches, Settings, Help).
# ABOUTME: Dispatches on the button label in any supported language.

from telegram import Update
from telegram.ext import ContextTypes

from src.commands import find, settings, watches
from src.commands import help as help_screen
from src.handlers import text_input
from src.ui.keyboard import MenuAction, menu_action


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    action = menu_action(update.message.text if update.message else None)
    if action is None:
        return
    text_input.clear_pending_input(context)
    if action is MenuAction.FIND:
        await find.find_command(update, context)
    elif action is MenuAction.WATCHES:
        await watches.watches_command(update, context)
    elif action is MenuAction.SETTINGS:
        await settings.settings_command(update, context)
    else:
        await help_screen.help_command(update, context)
