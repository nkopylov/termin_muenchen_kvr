# ABOUTME: Translates the bot's own text into English or Russian via t(key, lang, **params).
# ABOUTME: Merges per-area message catalogs and applies placeholders and plural forms.

import logging
from collections.abc import Iterable
from types import ModuleType

from src.i18n.locales import en, ru

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "ru")
DEFAULT_LANGUAGE = "en"

Message = str | dict[str, str]


def merge_catalogs(areas: Iterable[ModuleType]) -> dict[str, Message]:
    """Merge the MESSAGES of each area module, rejecting keys defined twice."""
    merged: dict[str, Message] = {}
    origin: dict[str, str] = {}
    for area in areas:
        for key, message in area.MESSAGES.items():
            if key in merged:
                raise ValueError(
                    f"Duplicate i18n key {key!r} in {area.__name__} "
                    f"(already defined in {origin[key]})"
                )
            merged[key] = message
            origin[key] = area.__name__
    return merged


CATALOGS: dict[str, dict[str, Message]] = {
    "en": merge_catalogs(en.AREAS),
    "ru": merge_catalogs(ru.AREAS),
}


def normalize_language(value: str | None) -> str:
    """Return a supported language code, falling back to English."""
    return value if value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def is_language_chosen(value: str | None) -> bool:
    """True when the stored value is a language the user picked."""
    return value in SUPPORTED_LANGUAGES


def plural_form(lang: str, count: int) -> str:
    """CLDR plural category for an integer count."""
    n = abs(int(count))
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "one" if n == 1 else "other"


def t(key: str, lang: str | None, **params: object) -> str:
    """Render the message for key in lang, falling back to English when missing."""
    lang = normalize_language(lang)
    message = CATALOGS[lang].get(key)
    if message is None and lang != DEFAULT_LANGUAGE:
        logger.warning("Missing %r translation for key %r", lang, key)
        lang = DEFAULT_LANGUAGE
        message = CATALOGS[lang].get(key)
    if message is None:
        raise KeyError(key)

    if isinstance(message, dict):
        if "count" not in params:
            raise KeyError(f"Plural message {key!r} needs a 'count' parameter")
        message = message[plural_form(lang, params["count"])]

    return message.format(**params)
