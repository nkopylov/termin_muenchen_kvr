# ABOUTME: The Telegram command list shown in the chat menu, per language and per chat.
# ABOUTME: English for everyone by default, Russian for Russian clients, the chosen language per chat.

import logging

from telegram import BotCommand, BotCommandScopeChat
from telegram.error import TelegramError

from src.i18n import DEFAULT_LANGUAGE, t

logger = logging.getLogger(__name__)

BOT_COMMANDS = ("start", "find", "watches", "settings", "help", "language", "stop")


def bot_commands(lang: str) -> list[BotCommand]:
    return [BotCommand(name, t(f"commands.{name}", lang)) for name in BOT_COMMANDS]


async def set_default_commands(bot) -> None:
    """English for everyone, Russian for clients whose Telegram language is Russian"""
    await bot.set_my_commands(bot_commands(DEFAULT_LANGUAGE))
    await bot.set_my_commands(bot_commands("ru"), language_code="ru")


async def set_chat_commands(bot, chat_id: int, lang: str) -> bool:
    """Command list of one chat in its user's language; False if Telegram refused"""
    try:
        await bot.set_my_commands(
            bot_commands(lang), scope=BotCommandScopeChat(chat_id)
        )
        return True
    except TelegramError as e:
        logger.warning(f"Could not set chat commands for chat {chat_id}: {e}")
        return False
