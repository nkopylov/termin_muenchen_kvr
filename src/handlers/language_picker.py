# ABOUTME: Builds and sends the bilingual language picker message.
# ABOUTME: Puts Russian first when Telegram's client language suggests a Russian speaker.

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.i18n import DEFAULT_LANGUAGE, t

RUSSIAN_LIKELY_CODES = ("ru", "uk", "be", "kk")


def language_order(telegram_language_code: str | None) -> tuple[str, str]:
    base = (telegram_language_code or "").lower().split("-")[0]
    return ("ru", "en") if base in RUSSIAN_LIKELY_CODES else ("en", "ru")


def build_language_picker(
    telegram_language_code: str | None,
) -> tuple[str, InlineKeyboardMarkup]:
    keyboard = [
        [
            InlineKeyboardButton(
                t(f"language.btn_{lang}", DEFAULT_LANGUAGE),
                callback_data=f"lang:{lang}",
            )
        ]
        for lang in language_order(telegram_language_code)
    ]
    return t("language.picker_prompt", DEFAULT_LANGUAGE), InlineKeyboardMarkup(keyboard)


async def send_language_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Send the picker as a new message in the update's chat."""
    text, markup = build_language_picker(update.effective_user.language_code)
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=text, reply_markup=markup
    )
