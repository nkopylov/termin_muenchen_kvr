# ABOUTME: Buttons of messages sent before the watches UI; routes them to the current screens.
# ABOUTME: Registered last, so it also catches any callback no other handler took.

from telegram import Update
from telegram.ext import ContextTypes


async def legacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError
