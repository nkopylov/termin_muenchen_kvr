# ABOUTME: Reads and stores a user's interface language in the DB and the per-user handler cache.
# ABOUTME: The cache key context.user_data["lang"] is only present once the user has chosen a language.

from typing import Any

from src.database import get_session
from src.i18n import is_language_chosen, normalize_language
from src.repositories import UserRepository

CACHE_KEY = "lang"


def _cache(context: Any) -> dict | None:
    return getattr(context, "user_data", None) if context is not None else None


def get_stored_language(user_id: int) -> str | None:
    """Raw language value from the DB, or None if the user is not registered."""
    with get_session() as session:
        user = UserRepository(session).get_user(user_id)
        return None if user is None else user.language


def get_user_language(user_id: int, context: Any = None) -> str:
    """The user's language ("en" or "ru"), English when unset or unknown."""
    cache = _cache(context)
    if cache is not None and CACHE_KEY in cache:
        return cache[CACHE_KEY]

    stored = get_stored_language(user_id)
    if is_language_chosen(stored) and cache is not None:
        cache[CACHE_KEY] = stored
    return normalize_language(stored)


def set_user_language(user_id: int, lang: str, context: Any = None) -> None:
    """Persist the user's choice and update the cache."""
    if not is_language_chosen(lang):
        raise ValueError(f"Unsupported language: {lang!r}")
    with get_session() as session:
        UserRepository(session).set_language(user_id, lang)
    cache = _cache(context)
    if cache is not None:
        cache[CACHE_KEY] = lang


def clear_cached_language(context: Any) -> None:
    cache = _cache(context)
    if cache is not None:
        cache.pop(CACHE_KEY, None)
