# ABOUTME: Applies the checker's alert decisions to Telegram and the database (push, edit, retire).
# ABOUTME: Also ends watches whose deadline passed or whose office disappeared, and expired bookings.

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Literal

from src.database import get_session
from src.i18n.user_language import get_user_language
from src.repositories import BookingSessionRepository, WatchRecord, WatchRepository
from src.services.analytics_service import track_event
from src.ui.telegram_safe import EditOutcome, safe_edit_text, safe_send
from src.watches import availability
from src.watches.alert_decision import (
    INTERACTION_LOCK,
    AlertAction,
    AlertDecision,
    decide_alert,
    interaction_state,
)
from src.watches.alert_ops import (
    alert_lock,
    close_live_alert,
    immediate_check_running,
    queue_retire,
)
from src.watches.alert_view import (
    BERLIN,
    FinalState,
    RenderedAlert,
    render_alert,
    render_booking_timed_out,
    render_ended,
    render_outdated,
)
from src.watches.slots import WatchSnapshot, prune_past
from src.watches.when import effective_window

logger = logging.getLogger(__name__)


def _berlin_date(now: datetime) -> date:
    return now.replace(tzinfo=UTC).astimezone(BERLIN).date()


def office_gone(rec: WatchRecord) -> bool:
    """The service has no public office, or the watch's office is not one of them."""
    public = availability.public_office_ids(rec.service_id)
    return not public or (rec.office_id is not None and rec.office_id not in public)


def _end_reason_holds(rec: WatchRecord, reason: str, now: datetime) -> bool:
    if reason == "deadline":
        return effective_window(rec.when, _berlin_date(now)) is None
    return office_gone(rec)


def _get(watch_id: int) -> WatchRecord | None:
    with get_session() as session:
        return WatchRepository(session).get(watch_id)


async def _user_blocked(user_id: int) -> None:
    with get_session() as session:
        paused = WatchRepository(session).pause_all_for_user(user_id, reason="blocked")
    logger.info(f"User {user_id} blocked the bot; paused {paused} watch(es)")
    await track_event("user_blocked_bot", user_id=user_id)


async def _push(
    bot,
    rec: WatchRecord,
    rendered: RenderedAlert,
    decision: AlertDecision,
    snapshot: WatchSnapshot,
    lang: str,
    now: datetime,
) -> bool:
    message, outcome = await safe_send(
        bot, rec.user_id, rendered.text, rendered.markup, silent=decision.silent
    )
    if outcome is EditOutcome.FORBIDDEN:
        await _user_blocked(rec.user_id)
        return False
    if message is None:
        return False

    fresh = _get(rec.id)
    if fresh is None:
        return False  # the user deleted their data during the send
    # A tap recorded during the send was on the previous live alert
    tapped_at = fresh.interacted_at
    tapped_meanwhile = tapped_at is not None and tapped_at != rec.interacted_at
    with get_session() as session:
        watches = WatchRepository(session)
        watches.set_live_alert(
            rec.id,
            message.chat_id,
            message.message_id,
            rendered.kind,
            snapshot.slots,
            decision.alerted,
            rendered.render_hash,
        )
        if tapped_meanwhile:
            watches.mark_interaction(message.chat_id, message.message_id, tapped_at)
    if decision.retire_previous and rec.live is not None:
        not_before = tapped_at + INTERACTION_LOCK if tapped_meanwhile else now
        queue_retire(
            rec.user_id,
            rec.live.chat_id,
            rec.live.message_id,
            render_outdated(lang),
            not_before,
        )
    await track_event(
        "notification_sent",
        user_id=rec.user_id,
        service_id=rec.service_id,
        notification_type="silent" if decision.silent else "push",
        slots_count=len(snapshot.days()),
    )
    return True


async def _edit(
    bot,
    rec: WatchRecord,
    rendered: RenderedAlert,
    decision: AlertDecision,
    snapshot: WatchSnapshot,
) -> bool:
    outcome = await safe_edit_text(
        bot, rec.live.chat_id, rec.live.message_id, rendered.text, rendered.markup
    )
    if outcome is EditOutcome.FORBIDDEN:
        await _user_blocked(rec.user_id)
        return False
    if outcome is EditOutcome.FAILED:
        return False
    with get_session() as session:
        watches = WatchRepository(session)
        if outcome is EditOutcome.GONE:
            watches.clear_live_alert(
                rec.id, reset_alerted=False, alerted=decision.alerted
            )
        else:
            watches.update_live_alert(
                rec.id,
                rendered.kind,
                snapshot.slots,
                decision.alerted,
                rendered.render_hash,
            )
    return outcome is not EditOutcome.GONE


async def apply_alert(
    bot,
    watch_id: int,
    snapshot: WatchSnapshot,
    now: datetime,
    booking_active: Callable[[int], bool],
) -> AlertAction:
    """Decide and carry out what the watch's live alert needs after a check; returns the
    action taken (NOOP when nothing was sent or edited, also after a Telegram failure)."""
    if not snapshot.ok:
        return AlertAction.NOOP
    async with alert_lock(watch_id):
        rec = _get(watch_id)
        if rec is None or rec.status != "active":
            return AlertAction.NOOP
        # Changed or re-checked by the user while this check was running
        if rec.snapshot != snapshot or immediate_check_running(watch_id):
            return AlertAction.NOOP

        interaction = interaction_state(
            booking_active(rec.user_id), rec.interacted_at, now
        )
        lang = get_user_language(rec.user_id)
        rendered = render_alert(rec, snapshot, lang, initial=False)
        live = rec.live
        decision = decide_alert(
            alerted=prune_past(rec.alerted, _berlin_date(now)),
            current=snapshot.slots,
            live_kind=live.kind if live else None,
            shown=live.shown if live else frozenset(),
            render_changed=live is not None
            and live.render_hash != rendered.render_hash,
            interaction=interaction,
        )

        match decision.action:
            case AlertAction.DEFER:
                return AlertAction.DEFER
            case AlertAction.PUSH:
                done = await _push(bot, rec, rendered, decision, snapshot, lang, now)
                return AlertAction.PUSH if done else AlertAction.NOOP
            case AlertAction.EDIT | AlertAction.EDIT_EMPTY:
                done = await _edit(bot, rec, rendered, decision, snapshot)
            case _:
                done = True
                if decision.alerted is not None and decision.alerted != rec.alerted:
                    with get_session() as session:
                        WatchRepository(session).set_alerted(watch_id, decision.alerted)

        if done and decision.clear_interaction:
            with get_session() as session:
                WatchRepository(session).clear_interaction(
                    watch_id, seen=rec.interacted_at
                )
        return decision.action if done else AlertAction.NOOP


async def end_watch_by_checker(
    bot,
    watch_id: int,
    reason: Literal["deadline", "gone"],
    now: datetime,
    booking_active: Callable[[int], bool],
) -> bool:
    """End an open watch; an active one gets its alert finalized and a silent S17/S17g
    message registered as its live alert, a paused one ends without any message."""
    async with alert_lock(watch_id):
        rec = _get(watch_id)
        if rec is None or not rec.is_open:
            return False
        if not _end_reason_holds(rec, reason, now):
            return False
        with get_session() as session:
            WatchRepository(session).set_status(watch_id, "ended", end_reason=reason)
        lang = get_user_language(rec.user_id)
        await close_live_alert(bot, watch_id, FinalState(reason), lang, by_user=False)
        if rec.status != "active":
            return True

        ended = _get(watch_id)
        rendered = render_ended(ended, lang)
        message, outcome = await safe_send(
            bot, rec.user_id, rendered.text, rendered.markup, silent=True
        )
        if outcome is EditOutcome.FORBIDDEN:
            await _user_blocked(rec.user_id)
        elif message is not None:
            with get_session() as session:
                WatchRepository(session).set_live_alert(
                    watch_id,
                    message.chat_id,
                    message.message_id,
                    rendered.kind,
                    frozenset(),
                    frozenset(),
                    rendered.render_hash,
                )
        logger.info(f"Watch {watch_id} of user {rec.user_id} ended: {reason}")
        return True


async def cleanup_expired_bookings(bot) -> int:
    """Delete expired booking sessions and tell their users; returns how many were removed."""
    with get_session() as session:
        expired = BookingSessionRepository(session).pop_expired_sessions()
    for booking in expired:
        if booking.message_id is None:
            continue
        lang = get_user_language(booking.user_id)
        await safe_edit_text(
            bot, booking.user_id, booking.message_id, render_booking_timed_out(lang)
        )
    return len(expired)
