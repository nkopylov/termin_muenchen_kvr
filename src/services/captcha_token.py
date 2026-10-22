# ABOUTME: Shared captcha token cache for every city API call (checker, immediate checks, booking).
# ABOUTME: Solves a new ALTCHA token only when the cached one has too little lifetime left.

import logging
import time
from collections.abc import Iterable

from src.services.locks import keyed_lock
from src.termin_tracker import get_fresh_captcha_token

logger = logging.getLogger(__name__)

# The city's tokens live 300 s; 280 s leaves a margin for clock skew
TOKEN_TTL_SECONDS = 280.0
TOKEN_ERROR_CODES = frozenset({"captchaInvalid", "captchaExpired", "captchaMissing"})

_clock = time.monotonic
_solve = get_fresh_captcha_token

_token: str | None = None
_expires_at: float = 0.0
_last_solve_ms: int | None = None


def is_token_error(codes: Iterable[str]) -> bool:
    return any(code in TOKEN_ERROR_CODES for code in codes)


def invalidate() -> None:
    """Forget the cached token, e.g. after the API rejected it."""
    global _token, _expires_at
    _token = None
    _expires_at = 0.0


def last_solve_ms() -> int | None:
    return _last_solve_ms


def _cached(min_ttl: float) -> str | None:
    if _token is not None and _expires_at - _clock() >= min_ttl:
        return _token
    return None


async def get_token(min_ttl: float = 30.0) -> str | None:
    """A token valid for at least `min_ttl` more seconds, or None if one cannot be solved."""
    global _token, _expires_at, _last_solve_ms
    if (token := _cached(min_ttl)) is not None:
        return token

    async with keyed_lock("captcha", "token"):
        if (token := _cached(min_ttl)) is not None:
            return token
        started = _clock()
        try:
            token = await _solve()
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.error(f"Captcha token could not be solved: {e}")
            token = None
        _last_solve_ms = int((_clock() - started) * 1000)
        if not token:
            invalidate()
            return None
        _token = token
        _expires_at = started + TOKEN_TTL_SECONDS
        return token
