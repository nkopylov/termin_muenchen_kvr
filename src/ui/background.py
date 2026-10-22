# ABOUTME: Runs slow per-user work (captcha, HTTP) outside the update queue, in order per user.
# ABOUTME: Exceptions of these tasks reach the application's error handler.

import asyncio
from collections.abc import Coroutine

from src.services.locks import keyed_lock


def user_lock(user_id: int) -> asyncio.Lock:
    return keyed_lock("user", user_id)


def run_for_user(context, update, user_id: int, coro: Coroutine) -> None:
    """Start `coro` as an application task; one user's tasks run one after another."""

    async def _locked() -> None:
        async with user_lock(user_id):
            await coro

    context.application.create_task(_locked(), update=update)
