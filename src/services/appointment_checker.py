# ABOUTME: Background checker: one city query per service per cycle for all active watches, then
# ABOUTME: alert updates per watch; also ends finished watches, keeps stats and sends health alerts.

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from telegram.error import TelegramError
from telegram.ext import Application

from src import services_manager
from src.config import get_config
from src.database import get_session
from src.repositories import (
    AppointmentLogRepository,
    WatchRecord,
    WatchRepository,
)
from src.services.alert_lifecycle import (
    apply_alert,
    cleanup_expired_bookings,
    end_watch_by_checker,
    office_gone,
)
from src.services.analytics_service import track_event
from src.services.queue_manager import is_user_in_queue
from src.watches import availability, when
from src.watches.alert_decision import AlertAction
from src.watches.alert_ops import process_pending_retires
from src.watches.availability import ApiError
from src.watches.slots import (
    SlotTime,
    WatchSnapshot,
    calendar_times,
    slots_in_scope,
    times_for_offices,
)
from src.watches.when import Window, effective_window

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
CATALOG_REFRESH_INTERVAL = timedelta(hours=6)
CATALOG_RETRY_INTERVAL = timedelta(minutes=1)

# Notfall-Hilfe Aufenthaltstitel: the city releases these slots on quarter-hour marks and they are
# taken within about two minutes, so they get extra checks right after each mark.
BURST_SERVICE_IDS = frozenset({10339027, 10339028})
BURST_OFFSETS = (
    timedelta(seconds=5),
    timedelta(seconds=20),
    timedelta(seconds=40),
    timedelta(seconds=70),
)
QUARTER_HOUR = timedelta(minutes=15)


def next_burst_at(now: datetime) -> datetime:
    """The first burst check moment strictly after now."""
    mark = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    for quarter in (mark, mark + QUARTER_HOUR):
        for offset in BURST_OFFSETS:
            if quarter + offset > now:
                return quarter + offset
    raise AssertionError("unreachable: the next quarter hour always has a later offset")


def next_wake(now: datetime, regular_due: datetime) -> tuple[datetime, bool]:
    """When the checker loop wakes next, and whether that wake is a burst check."""
    burst = next_burst_at(now)
    if burst < regular_due:
        return burst, True
    return regular_due, False


# Global stats tracking
stats = {
    "total_checks": 0,
    "successful_checks": 0,
    "failed_checks": 0,
    "appointments_found_count": 0,
    "bookings_started": 0,
    "bookings_completed": 0,
    "last_check_time": None,
    "last_success_time": None,
    "bot_start_time": None,
}

_catalog_refreshed_at: datetime | None = None
_paused_swept_on: date | None = None


def get_stats() -> dict:
    """Get current statistics"""
    return stats


def set_bot_start_time() -> None:
    """Set bot start time in stats"""
    stats["bot_start_time"] = datetime.now()


def increment_bookings_started() -> None:
    """Increment bookings started counter"""
    stats["bookings_started"] += 1


def increment_bookings_completed() -> None:
    """Increment bookings completed counter"""
    stats["bookings_completed"] += 1


async def send_health_alert(
    application: Application, message: str, title: str = "⚠️ <b>Health Alert</b>"
) -> None:
    """Send health alert to admin if configured"""
    config = get_config()
    if config.admin_telegram_id:
        try:
            await application.bot.send_message(
                chat_id=config.admin_telegram_id,
                text=f"{title}\n\n{message}",
                parse_mode="HTML",
            )
            logger.info(f"Sent health alert to admin {config.admin_telegram_id}")
        except TelegramError as e:
            logger.error(f"Failed to send health alert: {e}")


@dataclass
class CycleResult:
    checks: int = 0  # calendar queries, one per service
    successful: int = 0
    failed: int = 0
    trailing_failures: int = 0  # failed queries after the last successful one
    appointments_found: int = 0  # services with free days
    pushes: int = 0
    edits: int = 0
    ended: int = 0
    last_error: str | None = None

    def query_ok(self) -> None:
        self.checks += 1
        self.successful += 1
        self.trailing_failures = 0

    def query_failed(self, error: str) -> None:
        self.checks += 1
        self.failed += 1
        self.trailing_failures += 1
        self.last_error = error


async def _refresh_catalog_if_due(now: datetime) -> None:
    """Every 6 h; every minute while the catalog could not be loaded at all."""
    global _catalog_refreshed_at
    loaded = services_manager.catalog_loaded()
    if _catalog_refreshed_at is None and loaded:
        _catalog_refreshed_at = now
        return
    interval = CATALOG_REFRESH_INTERVAL if loaded else CATALOG_RETRY_INTERVAL
    if _catalog_refreshed_at is not None and now - _catalog_refreshed_at < interval:
        return
    _catalog_refreshed_at = now
    await asyncio.to_thread(services_manager.refresh_catalog)


async def _end_paused_past_deadline(bot, today: date, now: datetime) -> int:
    """Paused watches can only pass their deadline when the date changes: sweep once a day."""
    global _paused_swept_on
    if _paused_swept_on == today:
        return 0
    _paused_swept_on = today
    with get_session() as session:
        due = [
            rec.id
            for rec in WatchRepository(session).list_paused()
            if effective_window(rec.when, today) is None
        ]
    ended = 0
    for watch_id in due:
        ended += await end_watch_by_checker(bot, watch_id, "deadline", now)
    return ended


async def _end_finished(
    bot, active: list[WatchRecord], today: date, now: datetime, result: CycleResult
) -> list[tuple[WatchRecord, Window]]:
    """End watches past their deadline or without a public office; return the rest with
    their search windows. A user in booking keeps everything until the booking ends."""
    catalog_loaded = services_manager.catalog_loaded()
    remaining = []
    for rec in active:
        window = effective_window(rec.when, today)
        reason = None
        if window is None:
            reason = "deadline"
        elif catalog_loaded and office_gone(rec):
            reason = "gone"
        if reason is None:
            if not window.is_empty:
                remaining.append((rec, window))
        elif not is_user_in_queue(rec.user_id):
            result.ended += await end_watch_by_checker(bot, rec.id, reason, now)
    return remaining


def _log_free_days(service_id: int, office_ids: list[int], data: dict) -> None:
    office_id = office_ids[0] if len(office_ids) == 1 else 0
    with get_session() as session:
        AppointmentLogRepository(session).log_appointment(service_id, office_id, data)


async def _snapshot(
    rec: WatchRecord,
    window: Window,
    data: dict,
    in_scope: set[int],
    day_times: dict[date, tuple[SlotTime, ...] | None],
    now: datetime,
) -> WatchSnapshot:
    offices = set(availability.watch_office_ids(rec)) & in_scope
    if not offices:
        return WatchSnapshot(now, False)
    slots = slots_in_scope(data, offices, window)
    if not slots:
        return WatchSnapshot(now, True)

    earliest = min(s.day for s in slots)
    times = calendar_times(data, earliest, offices)
    if times is None:
        if earliest not in day_times:
            day = Window(earliest, earliest)
            day_offices = sorted(
                s.office_id for s in slots_in_scope(data, in_scope, day)
            )
            day_times[earliest] = await availability.fetch_day_times(
                rec.service_id, day_offices, earliest
            )
        fetched = day_times[earliest]
        if fetched is None:
            return WatchSnapshot(now, False)
        times = times_for_offices(fetched, offices)
    return WatchSnapshot(now, True, slots, times)


async def _end_rejected(
    bot,
    watches: list[tuple[WatchRecord, Window]],
    rejected: frozenset[int],
    now: datetime,
) -> int:
    """End as gone the watches whose every office the city rejected for the service."""
    ended = 0
    for rec, _ in watches:
        offices = set(availability.watch_office_ids(rec))
        if offices and offices <= rejected and not is_user_in_queue(rec.user_id):
            ended += await end_watch_by_checker(bot, rec.id, "gone", now, rejected)
    return ended


async def _check_service(
    bot,
    service_id: int,
    watches: list[tuple[WatchRecord, Window]],
    now: datetime,
    result: CycleResult,
) -> None:
    office_ids = sorted(
        {o for rec, _ in watches for o in availability.watch_office_ids(rec)}
    )
    if not office_ids:
        return
    start = min(w.start for _, w in watches)
    end = max(w.end for _, w in watches)
    logger.info(
        f"Checking service {service_id} at {len(office_ids)} office(s) "
        f"from {start} to {end} for {len(watches)} watch(es)"
    )
    res, dropped = await availability.fetch_calendar_with_fallback(
        service_id, office_ids, start, end
    )
    all_rejected = res.error is ApiError.COMBINATION and dropped == set(office_ids)
    if not res.ok and not all_rejected:
        error = f"service {service_id}: {res.describe()}"
        logger.warning(f"Calendar query failed for {error}")
        result.query_failed(error)
        await track_event(
            "api_error",
            endpoint="available-calendar",
            error_type=str(res.error),
            error_message=error,
        )
        return

    result.query_ok()
    result.ended += await _end_rejected(bot, watches, frozenset(dropped), now)
    if all_rejected:
        return
    data = res.data
    if data.get("availableDays"):
        result.appointments_found += 1
        _log_free_days(service_id, office_ids, data)
        await track_event(
            "appointment_found",
            service_id=service_id,
            slots_count=len(data["availableDays"]),
            matched_watches=len(watches),
        )

    in_scope = set(office_ids) - dropped
    day_times: dict[date, tuple[SlotTime, ...] | None] = {}
    for rec, window in watches:
        snapshot = await _snapshot(rec, window, data, in_scope, day_times, now)
        if not snapshot.ok:
            continue
        with get_session() as session:
            repo = WatchRepository(session)
            current = repo.get(rec.id)
            # Deleted, or its office or time changed by the user while the query ran
            if (
                current is None
                or current.office_id != rec.office_id
                or current.when != rec.when
            ):
                continue
            repo.record_check(rec.id, snapshot)
        action = await apply_alert(bot, rec.id, snapshot, now, is_user_in_queue)
        if action is AlertAction.PUSH:
            result.pushes += 1
        elif action in (AlertAction.EDIT, AlertAction.EDIT_EMPTY):
            result.edits += 1


async def run_check_cycle(
    bot, today: date, now: datetime, services: frozenset[int] | None = None
) -> CycleResult:
    """One pass over all active watches, or only those of the given services"""
    result = CycleResult()
    await process_pending_retires(bot, now)
    await _refresh_catalog_if_due(now)
    await cleanup_expired_bookings(bot)

    with get_session() as session:
        active = WatchRepository(session).list_active()
    remaining = await _end_finished(bot, active, today, now, result)
    result.ended += await _end_paused_past_deadline(bot, today, now)

    by_service: dict[int, list[tuple[WatchRecord, Window]]] = defaultdict(list)
    for rec, window in remaining:
        if services is None or rec.service_id in services:
            by_service[rec.service_id].append((rec, window))
    for service_id, watches in by_service.items():
        await _check_service(bot, service_id, watches, now, result)

    # Previous alerts of this cycle's pushes lose their buttons only after every push
    await process_pending_retires(bot, now)
    return result


@dataclass
class HealthState:
    consecutive_failures: int = 0
    alerted: bool = False  # the admin was told about the current failure streak


async def check_iteration(
    application: Application,
    health: HealthState,
    services: frozenset[int] | None = None,
) -> None:
    """One loop iteration: a check cycle plus stats, analytics and health alerts."""
    batch_start_time = time.time()
    stats["last_check_time"] = datetime.now()
    result = CycleResult()
    last_error = None
    recovered_after = None

    try:
        result = await run_check_cycle(
            application.bot, when.today_berlin(), when.utcnow(), services
        )
        stats["total_checks"] += result.checks
        stats["successful_checks"] += result.successful
        stats["failed_checks"] += result.failed
        stats["appointments_found_count"] += result.appointments_found
        if result.successful:
            stats["last_success_time"] = datetime.now()
            if health.alerted:
                recovered_after = health.consecutive_failures
            health.consecutive_failures = result.trailing_failures
        else:
            health.consecutive_failures += result.failed
        last_error = result.last_error
    except Exception as e:
        logger.exception("Error in check cycle")
        stats["total_checks"] += 1
        stats["failed_checks"] += 1
        health.consecutive_failures += 1
        last_error = str(e)
        await track_event(
            "api_error",
            endpoint="check_and_notify",
            error_type="exception",
            error_message=str(e),
        )

    if recovered_after is not None:
        health.alerted = False
        await send_health_alert(
            application,
            f"Checks are working again after {recovered_after} failed checks.",
            title="✅ <b>Checks recovered</b>",
        )

    # One alert per failure streak; the recovery message above closes the streak
    if not health.alerted and health.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        health.alerted = True
        await send_health_alert(
            application,
            f"Bot has failed {health.consecutive_failures} consecutive checks!\n"
            f"Last error: {last_error}",
        )
        await track_event(
            "health_alert",
            alert_type="consecutive_failures",
            consecutive_failures=health.consecutive_failures,
        )

    if services is not None and result.checks == 0:
        return
    await track_event(
        "appointment_check_batch",
        total_checks=result.checks,
        successful_checks=result.successful,
        failed_checks=result.failed,
        appointments_found=result.appointments_found,
        duration_ms=int((time.time() - batch_start_time) * 1000),
    )


async def check_and_notify(application: Application) -> None:
    """Background task: a check cycle every check_interval seconds, plus burst checks of the
    Notfall services right after each quarter-hour mark, forever."""
    config = get_config()
    health = HealthState()
    while True:
        await check_iteration(application, health)
        regular_due = when.utcnow() + timedelta(seconds=config.check_interval)
        while True:
            now = when.utcnow()
            wake, burst = next_wake(now, regular_due)
            await asyncio.sleep(max(0.0, (wake - now).total_seconds()))
            if not burst:
                break
            await check_iteration(application, health, services=BURST_SERVICE_IDS)
