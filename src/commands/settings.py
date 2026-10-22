# ABOUTME: Settings screen: language, saved booking details and deleting all data.
# ABOUTME: Entry points for /settings and every "s1:" button.

from telegram import Update
from telegram.ext import ContextTypes


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every "s1:" button"""
    raise NotImplementedError
