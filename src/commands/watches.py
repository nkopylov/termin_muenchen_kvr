# ABOUTME: My watches screen: one line per watch with its state and buttons to change, pause or stop.
# ABOUTME: Entry points for /watches, its alias commands and every "w1:" button.

from datetime import datetime

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


async def watches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/watches, /myservices, /status, /setdates and the reply keyboard's My watches button"""
    raise NotImplementedError


async def watches_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every "w1:" button"""
    raise NotImplementedError


def build_watches_screen(
    user_id: int, lang: str, now: datetime
) -> tuple[str, InlineKeyboardMarkup]:
    raise NotImplementedError
