# ABOUTME: Plain text messages: a typed date answer when one is awaited, otherwise a service search.
# ABOUTME: The awaited answer lives in context.user_data[AWAIT_KEY].

from telegram import Update
from telegram.ext import ContextTypes

AWAIT_KEY = "await_date"


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError


def clear_pending_input(context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError
