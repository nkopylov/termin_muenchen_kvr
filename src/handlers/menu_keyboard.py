# ABOUTME: Taps on the persistent reply keyboard (Find, My watches, Settings, Help).
# ABOUTME: Dispatches on the button label in any supported language.

from telegram import Update
from telegram.ext import ContextTypes


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError
