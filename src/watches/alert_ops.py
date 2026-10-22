# ABOUTME: Operations on a watch's live alert message: the per-watch lock, closing it with a final
# ABOUTME: text, and the queue of messages that must lose their buttons once no longer in use.

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from src.database import get_session
from src.repositories import (
    BookingSessionRepository,
    PendingRetireRepository,
    WatchRepository,
)
from src.services.locks import keyed_lock
from src.ui.telegram_safe import EditOutcome, safe_edit_text
from src.watches import when
from src.watches.alert_decision import INTERACTION_LOCK
from src.watches.alert_view import FinalState, render_final

logger = logging.getLogger(__name__)

MAX_RETIRE_ATTEMPTS = 6

_immediate_checks: set[int] = set()


def alert_lock(watch_id: int) -> asyncio.Lock:
    """Held by every writer of a watch's live-alert fields."""
    return keyed_lock("alert", watch_id)


@contextmanager
def running_immediate_check(watch_id: int) -> Iterator[None]:
    """Marks a watch whose check right after a user change is running; the checker
    leaves its alert alone meanwhile, since that check shows the newer result."""
    _immediate_checks.add(watch_id)
    try:
        yield
    finally:
        _immediate_checks.discard(watch_id)


def immediate_check_running(watch_id: int) -> bool:
    return watch_id in _immediate_checks


def queue_retire(
    user_id: int, chat_id: int, message_id: int, text: str, not_before: datetime
) -> None:
    with get_session() as session:
        PendingRetireRepository(session).add(
            user_id, chat_id, message_id, text, not_before
        )


def _in_use_until(rec, now: datetime) -> datetime | None:
    """When the user stops using the live alert, or None if they are not using it now."""
    with get_session() as session:
        booking = BookingSessionRepository(session).get_active(rec.user_id)
    if booking is not None:
        return booking.expires_at
    if rec.interacted_at is not None and now - rec.interacted_at < INTERACTION_LOCK:
        return rec.interacted_at + INTERACTION_LOCK
    return None


async def close_live_alert(
    bot, watch_id: int, final: FinalState, lang: str, *, by_user: bool
) -> None:
    """Edit the live alert to its final text and detach it; the caller holds alert_lock.
    Checker-initiated closes (by_user=False) wait while the user is using the message."""
    with get_session() as session:
        rec = WatchRepository(session).get(watch_id)
    if rec is None or rec.live is None:
        return

    now = when.utcnow()
    live = rec.live
    text = render_final(rec, final, lang)
    busy_until = None if by_user else _in_use_until(rec, now)
    if busy_until is not None:
        queue_retire(rec.user_id, live.chat_id, live.message_id, text, busy_until)
    else:
        outcome = await safe_edit_text(bot, live.chat_id, live.message_id, text)
        if outcome is EditOutcome.FAILED:
            queue_retire(rec.user_id, live.chat_id, live.message_id, text, now)

    with get_session() as session:
        WatchRepository(session).clear_live_alert(watch_id, reset_alerted=True)


async def process_pending_retires(bot, now: datetime) -> int:
    """Edit due queued messages to their final text; returns how many were finished."""
    with get_session() as session:
        due_ids = [item.id for item in PendingRetireRepository(session).due(now)]

    finished = 0
    for retire_id in due_ids:
        # Re-read right before the edit: a tap or a Book tap may have changed the row
        # while earlier edits were awaited.
        with get_session() as session:
            retires = PendingRetireRepository(session)
            item = retires.get(retire_id)
            if item is None or item.not_before > now:
                continue
            booking = BookingSessionRepository(session).get_active(item.user_id)
            if (
                booking is not None
                and booking.user_id == item.chat_id
                and booking.message_id == item.message_id
            ):
                retires.reschedule(item.id, booking.expires_at)
                continue

        outcome = await safe_edit_text(bot, item.chat_id, item.message_id, item.text)
        with get_session() as session:
            retires = PendingRetireRepository(session)
            if outcome is not EditOutcome.FAILED:
                retires.delete(item.id)
                finished += 1
                continue
            attempts = item.attempts + 1
            if attempts >= MAX_RETIRE_ATTEMPTS:
                retires.delete(item.id)
                logger.warning(
                    f"Retire of message {item.message_id} in chat {item.chat_id}: "
                    f"gave up after {attempts} attempts"
                )
                continue
            retires.reschedule(item.id, now + timedelta(minutes=2**attempts), attempts)
    return finished
