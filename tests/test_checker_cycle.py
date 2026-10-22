# ABOUTME: Tests for one checker cycle over all active watches and for the checker loop's health
# ABOUTME: tracking. The city API is replaced by scripted availability results; DB is in-memory.

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session

from src import services_manager
from src.config import get_config
from src.munich_api_client import ApiResponse
from src.repositories import (
    AppointmentLogRepository,
    BookingSessionRepository,
    PendingRetireRepository,
    UserRepository,
    WatchRepository,
)
from src.services import appointment_checker
from src.services.appointment_checker import (
    HealthState,
    check_iteration,
    run_check_cycle,
)
from src.watches.alert_decision import INTERACTION_LOCK
from src.watches.alert_ops import alert_lock
from src.watches.alert_view import (
    render_alert,
    render_booking_timed_out,
    render_ended,
    render_outdated,
)
from src.watches.availability import ApiError, CallResult
from src.watches.slots import Slot, SlotTime, WatchSnapshot
from src.watches.when import PRESETS, WhenSpec
from tests.conftest import BUERGERBUERO, NOW, TODAY
from tests.fakes import FakeApplication, FakeBot, calendar

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("catalog", "today", "clock")]

BERLIN = ZoneInfo("Europe/Berlin")
U1, U2, U3 = 101, 202, 303
SERVICE = 1063475
OTHER_SERVICE = 1063441
A, B = 102526, 10489
D1, D5 = date(2026, 10, 29), date(2026, 12, 15)
ALL_OFFICES = sorted(BUERGERBUERO)
LIVE = 500


def ts(day: date, hour: int, minute: int = 0) -> int:
    return int(
        datetime(day.year, day.month, day.day, hour, minute, tzinfo=BERLIN).timestamp()
    )


def ok(data: dict) -> CallResult:
    return CallResult(True, data, None)


def by_service(results: dict[int, CallResult]):
    return lambda service_id, _offices: results[service_id]


def add_user(db, user_id, lang="en"):
    with Session(db) as session:
        UserRepository(session).create_user(user_id, language=lang)


def add_watch(db, user_id, service_id=SERVICE, office_id=None, when=PRESETS["asap"]):
    with Session(db) as session:
        rec, _ = WatchRepository(session).create_or_update(
            user_id, service_id, office_id, when
        )
        return rec.id


def get(db, watch_id):
    with Session(db) as session:
        return WatchRepository(session).get(watch_id)


def sent_to(bot, user_id):
    return [c for c in bot.sent if c.chat_id == user_id]


@pytest.fixture(autouse=True)
def fresh_checker_state(monkeypatch):
    monkeypatch.setattr(appointment_checker, "_catalog_refreshed_at", None)
    monkeypatch.setattr(appointment_checker, "_paused_swept_on", None)
    refreshes = []
    monkeypatch.setattr(
        services_manager, "refresh_catalog", lambda: refreshes.append(1) or True
    )
    return refreshes


@pytest.fixture
def bot():
    return FakeBot()


async def cycle(bot, now=NOW, today=TODAY):
    return await run_check_cycle(bot, today, now)


class TestGrouping:
    async def test_one_calendar_call_per_service_serves_every_watch(
        self, db, bot, fake_availability
    ):
        for user in (U1, U2, U3):
            add_user(db, user)
        any_office = add_watch(db, U1)
        office_a_2w = add_watch(db, U2, office_id=A, when=PRESETS["2w"])
        office_b_late = add_watch(
            db,
            U3,
            office_id=B,
            when=WhenSpec("between", date_from=date(2026, 11, 2), date_to=D5),
        )
        other = add_watch(db, U1, service_id=OTHER_SERVICE, office_id=A)
        d1_times = [(ts(D1, 9), A), (ts(D1, 10), B)]
        fake_availability.calendar_results = [
            by_service(
                {
                    SERVICE: ok(
                        calendar(
                            {D1.isoformat(): [A, B], D5.isoformat(): [A]},
                            {D1.isoformat(): d1_times},
                        )
                    ),
                    OTHER_SERVICE: ok(calendar()),
                }
            )
        ] * 2

        result = await cycle(bot)

        calls = sorted(fake_availability.calendar_calls)
        assert calls == [
            (OTHER_SERVICE, [A], TODAY, TODAY + timedelta(days=180), None),
            (SERVICE, ALL_OFFICES, TODAY, TODAY + timedelta(days=180), None),
        ]
        assert fake_availability.day_calls == []
        assert (result.checks, result.successful, result.failed) == (2, 2, 0)

        assert get(db, any_office).snapshot.slots == {
            Slot(D1, A),
            Slot(D1, B),
            Slot(D5, A),
        }
        assert get(db, any_office).snapshot.earliest_times == (
            SlotTime(ts(D1, 9), A),
            SlotTime(ts(D1, 10), B),
        )
        assert get(db, office_a_2w).snapshot.slots == {Slot(D1, A)}
        assert get(db, office_a_2w).snapshot.earliest_times == (SlotTime(ts(D1, 9), A),)
        assert get(db, office_b_late).snapshot == WatchSnapshot(NOW, True)
        assert get(db, other).snapshot == WatchSnapshot(NOW, True)
        assert get(db, other).last_checked_at == NOW

        assert len(sent_to(bot, U1)) == 1
        assert len(sent_to(bot, U2)) == 1
        assert sent_to(bot, U3) == []
        assert result.pushes == 2

    async def test_free_days_are_logged(self, db, bot, fake_availability):
        add_user(db, U1)
        add_watch(db, U1, office_id=A)
        data = calendar({D1.isoformat(): [A]}, {D1.isoformat(): [(ts(D1, 9), A)]})
        fake_availability.calendar_results = [ok(data)]

        result = await cycle(bot)

        assert result.appointments_found == 1
        with Session(db) as session:
            [log] = AppointmentLogRepository(session).get_recent_logs(SERVICE)
        assert log.office_id == A

    async def test_query_failure_is_counted_and_skips_the_service(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        watch_id = add_watch(db, U1)
        fake_availability.calendar_results = [CallResult(False, None, ApiError.OTHER)]

        result = await cycle(bot)

        assert (result.checks, result.successful, result.failed) == (1, 0, 1)
        assert bot.calls == []
        assert get(db, watch_id).last_checked_at is None


class TestEnds:
    async def test_non_public_office_ends_gone_and_is_never_queried(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        add_user(db, U2)
        gone = add_watch(db, U1, office_id=999)
        add_watch(db, U2, office_id=A)
        fake_availability.calendar_results = [ok(calendar())]

        result = await cycle(bot)

        rec = get(db, gone)
        assert (rec.status, rec.end_reason) == ("ended", "gone")
        [message] = sent_to(bot, U1)
        assert message.text == render_ended(rec, "en").text
        assert message.disable_notification is True
        assert [c[1] for c in fake_availability.calendar_calls] == [[A]]
        assert result.ended == 1

    async def test_service_without_public_offices_ends_gone(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        watch_id = add_watch(db, U1, service_id=1234567)

        await cycle(bot)

        assert get(db, watch_id).end_reason == "gone"
        assert fake_availability.calendar_calls == []

    async def test_range_beyond_the_horizon_is_kept_and_not_queried(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        later = WhenSpec(
            "between", date_from=date(2028, 1, 1), date_to=date(2028, 2, 1)
        )
        watch_id = add_watch(db, U1, when=later)

        result = await cycle(bot)

        assert get(db, watch_id).status == "active"
        assert fake_availability.calendar_calls == []
        assert bot.calls == [] and result.ended == 0

    async def test_unloaded_catalog_ends_nothing(
        self, db, bot, fake_availability, monkeypatch
    ):
        monkeypatch.setattr(
            services_manager,
            "_full_payload_cache",
            {"services": [], "offices": [], "relations": []},
        )
        add_user(db, U1)
        office_watch = add_watch(db, U1, office_id=A)
        any_watch = add_watch(db, U1, service_id=OTHER_SERVICE)
        fake_availability.calendar_results = [ok(calendar())]

        await cycle(bot)

        assert get(db, office_watch).status == "active"
        assert get(db, any_watch).status == "active"
        assert [c[:2] for c in fake_availability.calendar_calls] == [(SERVICE, [A])]

    async def test_deadline_passed_ends_with_silent_message(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        watch_id = add_watch(db, U1, when=WhenSpec("before", date_to=TODAY))

        result = await cycle(bot)

        rec = get(db, watch_id)
        assert (rec.status, rec.end_reason) == ("ended", "deadline")
        [message] = bot.sent
        assert message.text == render_ended(rec, "en").text
        assert message.disable_notification is True
        assert rec.live.message_id == message.message_id and rec.live.kind == "ended"
        assert fake_availability.calendar_calls == []
        assert result.ended == 1

    async def test_paused_watch_past_deadline_ends_without_message(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        watch_id = add_watch(db, U1, when=WhenSpec("before", date_to=TODAY))
        running = add_watch(
            db,
            U1,
            service_id=OTHER_SERVICE,
            when=WhenSpec("before", date_to=TODAY + timedelta(days=1)),
        )
        with Session(db) as session:
            watches = WatchRepository(session)
            watches.set_status(watch_id, "paused", pause_reason="user")
            watches.set_status(running, "paused", pause_reason="user")

        await cycle(bot)

        assert (get(db, watch_id).status, get(db, watch_id).end_reason) == (
            "ended",
            "deadline",
        )
        assert get(db, running).status == "paused"
        assert bot.calls == []

    async def test_booking_user_is_not_ended_and_deferred_until_booking_ends(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        past = add_watch(db, U1, when=WhenSpec("before", date_to=TODAY))
        open_watch = add_watch(db, U1, service_id=OTHER_SERVICE, office_id=A)
        with Session(db) as session:
            BookingSessionRepository(session).create_session(
                U1,
                "SELECTING_TIME",
                SERVICE,
                A,
                D1.isoformat(),
                "",
                NOW + timedelta(minutes=15),
            )
        data = calendar({D1.isoformat(): [A]}, {D1.isoformat(): [(ts(D1, 9), A)]})
        fake_availability.calendar_results = [ok(data), ok(data)]

        await cycle(bot)

        assert get(db, past).status == "active"
        assert bot.calls == []
        assert get(db, open_watch).snapshot.slots == {Slot(D1, A)}

        with Session(db) as session:
            BookingSessionRepository(session).delete_session(U1)
        await cycle(bot)

        assert get(db, past).end_reason == "deadline"
        assert len(bot.sent) == 2


class TestCombinationFallback:
    async def test_offices_rejected_alone_are_dropped_for_this_cycle(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        add_user(db, U2)
        any_office = add_watch(db, U1)
        office_a = add_watch(db, U2, office_id=A)
        d1 = D1.isoformat()

        def reply(_service_id, offices):
            if len(offices) > 1 or offices == [A]:
                return CallResult(False, None, ApiError.COMBINATION)
            if offices == [B]:
                return ok(calendar({d1: [B]}, {d1: [(ts(D1, 11), B)]}))
            return ok(calendar())

        fake_availability.calendar_results = [reply] * 8

        result = await cycle(bot)

        assert (result.successful, result.failed) == (1, 0)
        assert get(db, any_office).snapshot.slots == {Slot(D1, B)}
        assert get(db, office_a).last_checked_at is None
        assert sent_to(bot, U2) == []
        assert len(sent_to(bot, U1)) == 1


class TestDayTimes:
    def setup_watches(self, db):
        for user in (U1, U2, U3):
            add_user(db, user)
        return (
            add_watch(db, U1, office_id=A),
            add_watch(db, U2, office_id=B),
            add_watch(db, U3),
        )

    async def test_fetched_once_per_day_and_filtered_per_watch(
        self, db, bot, fake_availability
    ):
        office_a, office_b, any_office = self.setup_watches(db)
        fake_availability.calendar_results = [ok(calendar({D1.isoformat(): [A, B]}))]
        times = (SlotTime(ts(D1, 9), A), SlotTime(ts(D1, 10), B))
        fake_availability.day_results = [times]

        await cycle(bot)

        assert fake_availability.day_calls == [(SERVICE, sorted([A, B]), D1)]
        assert get(db, office_a).snapshot.earliest_times == (times[0],)
        assert get(db, office_b).snapshot.earliest_times == (times[1],)
        assert get(db, any_office).snapshot.earliest_times == times
        assert len(bot.sent) == 3

    async def test_failure_leaves_watches_unchecked(self, db, bot, fake_availability):
        watches = self.setup_watches(db)
        fake_availability.calendar_results = [ok(calendar({D1.isoformat(): [A, B]}))]
        fake_availability.day_results = [None]

        await cycle(bot)

        assert bot.calls == []
        assert all(get(db, w).last_checked_at is None for w in watches)


class TestAlertsThroughCycle:
    async def test_push_comes_before_retiring_the_previous_alert(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        watch_id = add_watch(db, U1, office_id=A)
        with Session(db) as session:
            WatchRepository(session).set_live_alert(
                watch_id, U1, LIVE, "empty", frozenset(), frozenset(), "h"
            )
        fake_availability.calendar_results = [
            ok(calendar({D1.isoformat(): [A]}, {D1.isoformat(): [(ts(D1, 9), A)]}))
        ]

        await cycle(bot)

        assert [(c.method, c.message_id) for c in bot.calls] == [
            ("send_message", 1000),
            ("edit_message_text", LIVE),
        ]
        assert bot.edits[0].text == render_outdated("en")
        assert get(db, watch_id).live.message_id == 1000

    async def test_interaction_defers_then_change_goes_to_new_silent_message(
        self, db, bot, clock, fake_availability
    ):
        add_user(db, U1)
        watch_id = add_watch(db, U1)
        d1 = D1.isoformat()
        first = calendar({d1: [A]}, {d1: [(ts(D1, 9), A)]})
        fake_availability.calendar_results = [ok(first)]
        await cycle(bot)
        [alert] = bot.sent
        with Session(db) as session:
            WatchRepository(session).mark_interaction(
                U1, alert.message_id, NOW + timedelta(minutes=1)
            )

        both = calendar({d1: [A, B]}, {d1: [(ts(D1, 9), A), (ts(D1, 10), B)]})
        fake_availability.calendar_results = [ok(both), ok(both)]
        clock.now = NOW + timedelta(minutes=5)
        await cycle(bot, now=clock.now)
        assert len(bot.calls) == 1

        clock.now = NOW + timedelta(minutes=1) + INTERACTION_LOCK
        await cycle(bot, now=clock.now)

        assert len(bot.sent) == 2
        assert bot.sent[1].disable_notification is True
        [retire] = bot.edits
        assert (retire.message_id, retire.text) == (
            alert.message_id,
            render_outdated("en"),
        )
        rec = get(db, watch_id)
        assert rec.live.message_id == bot.sent[1].message_id
        assert rec.live.shown == {Slot(D1, A), Slot(D1, B)}

    async def test_same_slots_twice_send_one_alert(self, db, bot, fake_availability):
        add_user(db, U1)
        watch_id = add_watch(db, U1)
        d1 = D1.isoformat()
        data = calendar({d1: [A]}, {d1: [(ts(D1, 9), A)]})
        fake_availability.calendar_results = [ok(data), ok(data)]

        await cycle(bot)
        await cycle(bot)

        [message] = bot.sent
        expected = render_alert(
            get(db, watch_id), get(db, watch_id).snapshot, "en", initial=False
        )
        assert message.text == expected.text
        assert bot.edits == []


async def until(condition):
    for _ in range(1000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition never met")


class TestUserChangesDuringCycle:
    @pytest.mark.parametrize(
        "change",
        [
            lambda watches, watch_id: watches.create_or_update(
                U1, SERVICE, A, PRESETS["asap"]
            ),
            lambda watches, watch_id: watches.set_when(
                watch_id, WhenSpec("before", date_to=date(2026, 11, 1))
            ),
        ],
        ids=["office", "time"],
    )
    async def test_change_during_query_leaves_the_user_check_alone(
        self, db, bot, fake_availability, change
    ):
        add_user(db, U1)
        watch_id = add_watch(db, U1)
        d1, d5 = D1.isoformat(), D5.isoformat()
        stale = calendar({d1: [A, B], d5: [A]}, {d1: [(ts(D1, 9), A), (ts(D1, 10), B)]})
        fake_availability.gate = asyncio.Event()
        fake_availability.calendar_results = [ok(stale)]
        running = asyncio.create_task(cycle(bot))
        await until(lambda: fake_availability.calendar_calls)

        fresh = WatchSnapshot(
            NOW, True, frozenset({Slot(D1, A)}), (SlotTime(ts(D1, 9), A),)
        )
        async with alert_lock(watch_id):
            with Session(db) as session:
                watches = WatchRepository(session)
                change(watches, watch_id)
                watches.record_check(watch_id, fresh)
                rec = watches.get(watch_id)
                watches.set_live_alert(
                    watch_id,
                    U1,
                    777,
                    "slots",
                    fresh.slots,
                    fresh.slots,
                    render_alert(rec, fresh, "en", initial=False).render_hash,
                )
        fake_availability.gate.set()
        await running

        assert bot.calls == []
        rec = get(db, watch_id)
        assert rec.snapshot == fresh
        assert rec.live.message_id == 777

    async def test_watch_reopened_while_another_ends_is_not_ended(
        self, db, bot, fake_availability
    ):
        add_user(db, U1)
        add_user(db, U2)
        first = add_watch(db, U1, when=WhenSpec("before", date_to=TODAY))
        second = add_watch(db, U2, when=WhenSpec("before", date_to=TODAY))
        gate = bot.gate("send_message")
        running = asyncio.create_task(cycle(bot))
        await until(lambda: get(db, first).status == "ended")

        with Session(db) as session:
            WatchRepository(session).set_when(second, PRESETS["asap"])
        gate.set()
        result = await running

        assert (get(db, second).status, get(db, second).end_reason) == ("active", None)
        assert [m.chat_id for m in bot.sent] == [U1]
        assert result.ended == 1


class TestHousekeeping:
    async def test_expired_booking_is_closed_in_the_same_cycle(
        self, db, bot, fake_availability
    ):
        add_user(db, U1, lang="ru")
        add_watch(db, U1, office_id=A)
        with Session(db) as session:
            BookingSessionRepository(session).create_session(
                U1,
                "ASKING_NAME",
                SERVICE,
                A,
                D1.isoformat(),
                "",
                NOW - timedelta(seconds=1),
                message_id=77,
            )
        d1 = D1.isoformat()
        fake_availability.calendar_results = [
            ok(calendar({d1: [A]}, {d1: [(ts(D1, 9), A)]}))
        ]

        await cycle(bot)

        timed_out = [e for e in bot.edits if e.message_id == 77]
        assert [e.text for e in timed_out] == [render_booking_timed_out("ru")]
        assert len(bot.sent) == 1
        with Session(db) as session:
            assert BookingSessionRepository(session).get_session(U1) is None

    async def test_due_retires_are_processed_without_watches(self, db, bot):
        with Session(db) as session:
            PendingRetireRepository(session).add(U1, U1, 42, "done", NOW)

        await cycle(bot)

        [edit] = bot.edits
        assert (edit.message_id, edit.text) == (42, "done")

    async def test_catalog_refreshed_every_six_hours(
        self, db, bot, fresh_checker_state
    ):
        await cycle(bot, now=NOW)
        await cycle(bot, now=NOW + timedelta(hours=1))
        assert fresh_checker_state == []
        await cycle(bot, now=NOW + timedelta(hours=6))
        await cycle(bot, now=NOW + timedelta(hours=7))
        assert fresh_checker_state == [1]

    async def test_unloaded_catalog_retried_every_minute(
        self, db, bot, fresh_checker_state, monkeypatch
    ):
        monkeypatch.setattr(services_manager, "_full_payload_cache", None)
        monkeypatch.setattr(services_manager, "_services_cache", None)
        await cycle(bot, now=NOW)
        await cycle(bot, now=NOW + timedelta(seconds=30))
        assert fresh_checker_state == [1]
        await cycle(bot, now=NOW + timedelta(minutes=1))
        assert fresh_checker_state == [1, 1]


ADMIN = 999000


@pytest.fixture
def fresh_stats(monkeypatch):
    stats = {
        key: 0 if isinstance(value, int) else None
        for key, value in appointment_checker.stats.items()
    }
    monkeypatch.setattr(appointment_checker, "stats", stats)
    monkeypatch.setattr(get_config(), "admin_telegram_id", ADMIN)
    return stats


class TestHealth:
    async def test_token_errors_are_retried_then_alert_admin_after_five_failures(
        self, db, fake_api, fake_token, fresh_stats, events
    ):
        events.patch(appointment_checker)
        add_user(db, U1)
        add_watch(db, U1, office_id=A)
        fake_api["get"] = [ApiResponse(None, 400, ("captchaInvalid",))] * 10
        bot = FakeBot()
        app = FakeApplication(bot)
        health = HealthState()

        for _ in range(4):
            await check_iteration(app, health)
        assert sent_to(bot, ADMIN) == []

        await check_iteration(app, health)

        assert len(fake_api["calls"]) == 10
        assert fake_token["invalidated"] == 10
        [alert] = sent_to(bot, ADMIN)
        assert "failed 5 consecutive checks" in alert.text
        assert health.consecutive_failures == 5
        assert (fresh_stats["total_checks"], fresh_stats["failed_checks"]) == (5, 5)
        assert (
            "health_alert",
            {
                "user_id": None,
                "alert_type": "consecutive_failures",
                "consecutive_failures": 5,
            },
        ) in events.calls

    async def test_success_resets_failures_and_updates_stats(
        self, db, fake_availability, fresh_stats, events
    ):
        events.patch(appointment_checker)
        add_user(db, U1)
        add_watch(db, U1, office_id=A)
        d1 = D1.isoformat()
        fake_availability.calendar_results = [
            ok(calendar({d1: [A]}, {d1: [(ts(D1, 9), A)]}))
        ]
        bot = FakeBot()
        health = HealthState(consecutive_failures=3)

        await check_iteration(FakeApplication(bot), health)

        assert health.consecutive_failures == 0
        assert fresh_stats["successful_checks"] == 1
        assert fresh_stats["appointments_found_count"] == 1
        assert fresh_stats["last_success_time"] is not None
        assert sent_to(bot, ADMIN) == []
        [batch] = [p for name, p in events.calls if name == "appointment_check_batch"]
        assert (
            batch["total_checks"],
            batch["successful_checks"],
            batch["appointments_found"],
        ) == (1, 1, 1)

    async def test_exception_counts_as_failure(
        self, db, fresh_stats, monkeypatch, caplog
    ):
        async def broken(bot, today, now):
            raise RuntimeError("boom")

        monkeypatch.setattr(appointment_checker, "run_check_cycle", broken)
        health = HealthState()

        with caplog.at_level(logging.ERROR, logger=appointment_checker.__name__):
            await check_iteration(FakeApplication(FakeBot()), health)

        assert health.consecutive_failures == 1
        assert fresh_stats["failed_checks"] == 1
        [record] = caplog.records
        assert record.getMessage() == "Error in check cycle"
        assert str(record.exc_info[1]) == "boom"
