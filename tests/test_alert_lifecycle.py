# ABOUTME: Tests for applying alert decisions to Telegram and the DB, checker-initiated watch ends
# ABOUTME: and expired booking cleanup. Real in-memory DB, recording FakeBot, fixed clock.

import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session
from telegram.error import BadRequest, Forbidden, NetworkError

from src.database import get_session
from src.handlers.interaction_tracker import record_interaction
from src.repositories import (
    BookingSessionRepository,
    PendingRetireRepository,
    UserRepository,
    WatchRepository,
)
from src.services import alert_lifecycle
from src.services.alert_lifecycle import (
    apply_alert,
    cleanup_expired_bookings,
    end_watch_by_checker,
)
from src.ui import callbacks as cb
from src.watches.alert_decision import INTERACTION_LOCK, AlertAction
from src.watches.alert_ops import alert_lock, process_pending_retires
from src.watches.alert_view import (
    FinalState,
    render_alert,
    render_booking_timed_out,
    render_empty_now,
    render_ended,
    render_final,
    render_outdated,
)
from src.watches.slots import Slot, SlotTime, WatchSnapshot
from src.watches.when import PRESETS, WhenSpec
from tests.conftest import NOW
from tests.fakes import FakeBot, make_callback_update

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("catalog")]

BERLIN = ZoneInfo("Europe/Berlin")
USER = 4242
OTHER = 5151
SERVICE = 1063475
A, B = 102526, 10489
D1, D2, D3, D4, D5 = (
    date(2026, 10, 29),
    date(2026, 10, 30),
    date(2026, 11, 2),
    date(2026, 11, 3),
    date(2026, 12, 15),
)
LIVE = 500


def ts(day: date, hour: int, minute: int = 0) -> int:
    return int(
        datetime(day.year, day.month, day.day, hour, minute, tzinfo=BERLIN).timestamp()
    )


def snap(*slots: Slot, ok: bool = True, times: tuple | None = None) -> WatchSnapshot:
    slot_set = frozenset(slots)
    if times is None and slot_set:
        earliest = min(s.day for s in slot_set)
        offices = sorted({s.office_id for s in slot_set if s.day == earliest})
        times = tuple(
            SlotTime(ts(earliest, 9, i * 5), o) for i, o in enumerate(offices)
        )
    return WatchSnapshot(NOW, ok, slot_set, times or ())


def never_booking(_user_id: int) -> bool:
    return False


def add_user(db, user_id=USER, lang="en"):
    with Session(db) as session:
        UserRepository(session).create_user(user_id, language=lang)


def add_watch(
    db, user_id=USER, service_id=SERVICE, office_id=None, when=PRESETS["asap"]
):
    with Session(db) as session:
        rec, _ = WatchRepository(session).create_or_update(
            user_id, service_id, office_id, when
        )
        return rec.id


def get(db, watch_id):
    with Session(db) as session:
        return WatchRepository(session).get(watch_id)


def make_live(db, watch_id, *slots, kind="slots", alerted=None, message_id=LIVE):
    """Register a live alert as the checker would have rendered it for `slots`."""
    rec = get(db, watch_id)
    shown = frozenset(slots)
    rendered = render_alert(rec, snap(*slots), "en", initial=False)
    with Session(db) as session:
        WatchRepository(session).set_live_alert(
            watch_id,
            rec.user_id,
            message_id,
            kind,
            shown if kind == "slots" else frozenset(),
            shown if alerted is None else frozenset(alerted),
            rendered.render_hash if kind == "slots" else "empty-hash",
        )


def tap(db, watch_id, at):
    rec = get(db, watch_id)
    with Session(db) as session:
        WatchRepository(session).mark_interaction(
            rec.live.chat_id, rec.live.message_id, at
        )


def queued(db, now):
    with Session(db) as session:
        return PendingRetireRepository(session).due(now)


def all_queued(db):
    return queued(db, NOW + timedelta(days=365))


def book_session(db, user_id=USER, expires_at=None, message_id=None):
    with Session(db) as session:
        BookingSessionRepository(session).create_session(
            user_id,
            "SELECTING_TIME",
            SERVICE,
            0,
            D1.isoformat(),
            "",
            expires_at or NOW + timedelta(minutes=15),
            message_id=message_id,
        )


@pytest.fixture
def watch(db, clock):
    add_user(db)
    return add_watch(db)


@pytest.fixture
def bot():
    return FakeBot()


def record(watch_id, snapshot):
    """Store the check as the checker does before applying it."""
    with get_session() as session:
        watches = WatchRepository(session)
        if watches.get(watch_id) is not None:
            watches.record_check(watch_id, snapshot)


async def apply(bot, watch_id, snapshot, now=NOW, booking_active=never_booking):
    record(watch_id, snapshot)
    return await apply_alert(bot, watch_id, snapshot, now, booking_active)


class TestPush:
    async def test_first_slots_push_with_sound_and_become_live(
        self, db, bot, watch, events
    ):
        events.patch(alert_lifecycle)
        snapshot = snap(Slot(D1, A), Slot(D2, B))

        action = await apply(bot, watch, snapshot)

        assert action is AlertAction.PUSH
        [sent] = bot.sent
        expected = render_alert(get(db, watch), snapshot, "en", initial=False)
        assert sent.chat_id == USER
        assert sent.text == expected.text
        assert sent.reply_markup == expected.markup
        assert sent.disable_notification is False
        rec = get(db, watch)
        assert rec.live.message_id == sent.message_id
        assert rec.live.kind == "slots"
        assert rec.live.shown == snapshot.slots
        assert rec.live.render_hash == expected.render_hash
        assert rec.alerted == snapshot.slots
        assert [name for name, _ in events.calls] == ["notification_sent"]

    async def test_push_in_user_language(self, db, bot, clock):
        add_user(db, lang="ru")
        watch_id = add_watch(db)
        snapshot = snap(Slot(D1, A))
        await apply(bot, watch_id, snapshot)
        [sent] = bot.sent
        assert (
            sent.text
            == render_alert(get(db, watch_id), snapshot, "ru", initial=False).text
        )

    async def test_slots_after_empty_alert_push_and_retire_it_later(
        self, db, bot, watch
    ):
        make_live(db, watch, kind="empty", alerted=())

        action = await apply(bot, watch, snap(Slot(D1, A)))

        assert action is AlertAction.PUSH
        assert len(bot.sent) == 1 and bot.edits == []
        [item] = queued(db, NOW)
        assert (item.chat_id, item.message_id) == (USER, LIVE)
        assert item.text == render_outdated("en")
        assert get(db, watch).live.message_id == bot.sent[0].message_id

    async def test_new_earlier_day_pushes_and_retires_previous(self, db, bot, watch):
        make_live(db, watch, Slot(D2, A))

        action = await apply(bot, watch, snap(Slot(D1, A), Slot(D2, A)))

        assert action is AlertAction.PUSH
        assert bot.sent[0].disable_notification is False
        assert [(i.message_id, i.text) for i in queued(db, NOW)] == [
            (LIVE, render_outdated("en"))
        ]
        rec = get(db, watch)
        assert rec.alerted == {Slot(D1, A), Slot(D2, A)}

    async def test_released_interaction_change_goes_to_silent_new_message(
        self, db, bot, watch
    ):
        make_live(db, watch, Slot(D1, A))
        tap(db, watch, NOW - INTERACTION_LOCK - timedelta(minutes=1))

        action = await apply(bot, watch, snap(Slot(D1, A), Slot(D1, B)))

        assert action is AlertAction.PUSH
        [sent] = bot.sent
        assert sent.disable_notification is True
        assert [i.message_id for i in queued(db, NOW)] == [LIVE]
        rec = get(db, watch)
        assert rec.live.message_id == sent.message_id
        assert rec.interacted_at is None

    async def test_past_alerted_days_are_pruned_before_deciding(self, db, bot, watch):
        yesterday = date(2026, 10, 21)
        make_live(db, watch, Slot(D1, A), alerted={Slot(yesterday, A), Slot(D1, A)})

        await apply(bot, watch, snap(Slot(D1, A), Slot(D1, B)))

        assert get(db, watch).alerted == {Slot(D1, A), Slot(D1, B)}


class TestEditAndNoop:
    async def test_second_office_on_alerted_day_edits_in_place(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        snapshot = snap(Slot(D1, A), Slot(D1, B))

        action = await apply(bot, watch, snapshot)

        assert action is AlertAction.EDIT
        assert bot.sent == []
        [edit] = bot.edits
        expected = render_alert(get(db, watch), snapshot, "en", initial=False)
        assert (edit.chat_id, edit.message_id) == (USER, LIVE)
        assert edit.text == expected.text
        assert edit.reply_markup == expected.markup
        rec = get(db, watch)
        assert rec.live.message_id == LIVE
        assert rec.live.shown == snapshot.slots
        assert rec.live.render_hash == expected.render_hash
        assert rec.alerted == snapshot.slots

    async def test_far_horizon_day_edits_without_push(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A), Slot(D2, A), Slot(D3, A))
        action = await apply(
            bot, watch, snap(Slot(D1, A), Slot(D2, A), Slot(D3, A), Slot(D5, A))
        )
        assert action is AlertAction.EDIT
        assert bot.sent == [] and len(bot.edits) == 1

    async def test_same_render_does_nothing(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        action = await apply(bot, watch, snap(Slot(D1, A)))
        assert action is AlertAction.NOOP
        assert bot.calls == []

    async def test_released_same_render_clears_interaction_only(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        tap(db, watch, NOW - INTERACTION_LOCK)
        action = await apply(bot, watch, snap(Slot(D1, A)))
        assert action is AlertAction.NOOP
        assert bot.calls == []
        assert get(db, watch).interacted_at is None

    async def test_deleted_alert_is_not_repeated(self, db, bot, watch):
        with Session(db) as session:
            WatchRepository(session).set_alerted(watch, frozenset({Slot(D1, A)}))

        action = await apply(bot, watch, snap(Slot(D1, A), Slot(D1, B)))

        assert action is AlertAction.NOOP
        assert bot.calls == []
        assert get(db, watch).alerted == {Slot(D1, A), Slot(D1, B)}

    async def test_slots_gone_edit_live_alert_to_empty(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))

        action = await apply(bot, watch, snap())

        assert action is AlertAction.EDIT_EMPTY
        [edit] = bot.edits
        expected = render_empty_now(get(db, watch), NOW, "en")
        assert edit.text == expected.text
        assert edit.reply_markup is None
        rec = get(db, watch)
        assert rec.live.kind == "empty"
        assert rec.live.shown == frozenset()
        assert rec.alerted == frozenset()

    async def test_released_going_empty_clears_interaction(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        tap(db, watch, NOW - INTERACTION_LOCK)
        await apply(bot, watch, snap())
        assert get(db, watch).interacted_at is None

    async def test_empty_after_empty_resets_alerted_only(self, db, bot, watch):
        make_live(db, watch, kind="empty", alerted=())
        action = await apply(bot, watch, snap())
        assert action is AlertAction.NOOP
        assert bot.calls == []

    async def test_empty_without_live_resets_alerted(self, db, bot, watch):
        with Session(db) as session:
            WatchRepository(session).set_alerted(watch, frozenset({Slot(D1, A)}))
        await apply(bot, watch, snap())
        assert bot.calls == []
        assert get(db, watch).alerted == frozenset()

    async def test_flapping_slots_push_once(self, db, bot, watch):
        both = snap(Slot(D1, A), Slot(D2, A))
        assert await apply(bot, watch, both) is AlertAction.PUSH
        assert await apply(bot, watch, snap(Slot(D1, A))) is AlertAction.EDIT
        assert await apply(bot, watch, both) is AlertAction.EDIT
        assert len(bot.sent) == 1


class TestDefer:
    async def test_recent_interaction_defers(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        tap(db, watch, NOW - INTERACTION_LOCK + timedelta(seconds=1))
        snapshot = snap(Slot(D1, A), Slot(D2, B))
        record(watch, snapshot)
        before = get(db, watch)

        action = await apply(bot, watch, snapshot)

        assert action is AlertAction.DEFER
        assert bot.calls == []
        assert get(db, watch) == before

    async def test_booking_defers(self, db, bot, watch):
        action = await apply(
            bot, watch, snap(Slot(D1, A)), booking_active=lambda uid: uid == USER
        )
        assert action is AlertAction.DEFER
        assert bot.calls == []
        assert get(db, watch).alerted == frozenset()

    async def test_interaction_recorded_after_snapshot_defers(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        snapshot = snap(Slot(D1, A), Slot(D2, A))
        await record_interaction(
            make_callback_update(cb.watch_stop(watch), USER, LIVE, bot=bot), None
        )
        assert await apply(bot, watch, snapshot) is AlertAction.DEFER
        assert bot.calls == []


class TestNotApplicable:
    async def test_failed_snapshot_changes_nothing(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        before = get(db, watch)
        assert await apply(bot, watch, snap(ok=False)) is AlertAction.NOOP
        assert bot.calls == []
        assert get(db, watch) == before

    async def test_missing_watch(self, db, bot, clock):
        assert await apply(bot, 999, snap(Slot(D1, A))) is AlertAction.NOOP
        assert bot.calls == []

    @pytest.mark.parametrize("status", ["paused", "ended"])
    async def test_not_active_watch(self, db, bot, watch, status):
        with Session(db) as session:
            WatchRepository(session).set_status(
                watch, status, pause_reason="user", end_reason="stopped"
            )
        assert await apply(bot, watch, snap(Slot(D1, A))) is AlertAction.NOOP
        assert bot.calls == []


class TestUserChangeDuringCheck:
    async def test_snapshot_replaced_while_waiting_for_lock_is_not_applied(
        self, db, bot, watch
    ):
        stale = snap(Slot(D1, B), Slot(D5, A))
        record(watch, stale)
        fresh = snap(Slot(D5, A))
        async with alert_lock(watch):
            task = asyncio.create_task(
                apply_alert(bot, watch, stale, NOW, never_booking)
            )
            await asyncio.sleep(0)
            with Session(db) as session:
                watches = WatchRepository(session)
                watches.set_office(watch, A)
                watches.record_check(watch, fresh)
            make_live(db, watch, Slot(D5, A), message_id=777)

        assert await task is AlertAction.NOOP
        assert bot.calls == []
        rec = get(db, watch)
        assert rec.snapshot == fresh
        assert rec.live.message_id == 777


class TestTelegramErrors:
    async def test_push_blocked_pauses_all_active_watches(self, db, bot, watch, events):
        events.patch(alert_lifecycle)
        second = add_watch(db, service_id=1063441)
        bot.fail_next("send_message", Forbidden("bot was blocked by the user"))

        action = await apply(bot, watch, snap(Slot(D1, A)))

        assert action is AlertAction.NOOP
        for watch_id in (watch, second):
            rec = get(db, watch_id)
            assert (rec.status, rec.pause_reason) == ("paused", "blocked")
        assert get(db, watch).live is None
        assert [name for name, _ in events.calls] == ["user_blocked_bot"]
        assert events.calls[0][1]["user_id"] == USER

    async def test_push_failure_leaves_state_for_next_cycle(self, db, bot, watch):
        bot.fail_next("send_message", NetworkError("down"))
        assert await apply(bot, watch, snap(Slot(D1, A))) is AlertAction.NOOP
        rec = get(db, watch)
        assert rec.live is None and rec.alerted == frozenset()

        assert await apply(bot, watch, snap(Slot(D1, A))) is AlertAction.PUSH
        assert len(bot.sent) == 1

    async def test_push_failure_keeps_previous_live_unretired(self, db, bot, watch):
        make_live(db, watch, kind="empty", alerted=())
        bot.fail_next("send_message", NetworkError("down"))
        await apply(bot, watch, snap(Slot(D1, A)))
        assert all_queued(db) == []
        assert get(db, watch).live.message_id == LIVE

    async def test_edit_of_deleted_message_detaches_and_does_not_repeat(
        self, db, bot, watch
    ):
        make_live(db, watch, Slot(D1, A))
        bot.fail_next("edit_message_text", BadRequest("Message to edit not found"))

        await apply(bot, watch, snap(Slot(D1, A), Slot(D1, B)))

        rec = get(db, watch)
        assert rec.live is None
        assert rec.alerted == {Slot(D1, A), Slot(D1, B)}
        assert (
            await apply(bot, watch, snap(Slot(D1, A), Slot(D1, B))) is AlertAction.NOOP
        )
        assert bot.sent == []

    async def test_edit_not_modified_still_records_render(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        bot.fail_next("edit_message_text", BadRequest("Message is not modified"))
        snapshot = snap(Slot(D1, A), Slot(D1, B))

        assert await apply(bot, watch, snapshot) is AlertAction.EDIT
        assert get(db, watch).live.shown == snapshot.slots

    async def test_edit_blocked_pauses(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        bot.fail_next("edit_message_text", Forbidden("bot was blocked by the user"))
        await apply(bot, watch, snap())
        rec = get(db, watch)
        assert (rec.status, rec.pause_reason) == ("paused", "blocked")

    async def test_edit_failure_changes_nothing(self, db, bot, watch):
        make_live(db, watch, Slot(D1, A))
        snapshot = snap()
        record(watch, snapshot)
        before = get(db, watch)
        bot.fail_next("edit_message_text", NetworkError("down"))
        assert await apply(bot, watch, snapshot) is AlertAction.NOOP
        assert get(db, watch) == before


class TestRaceWithTap:
    async def test_watch_deleted_during_push_is_not_written(self, db, bot, watch):
        gate = bot.gate("send_message")
        task = asyncio.create_task(apply(bot, watch, snap(Slot(D1, A))))
        await asyncio.sleep(0)
        with Session(db) as session:
            UserRepository(session).delete_user_cascade(USER)
        gate.set()

        assert await task is AlertAction.NOOP
        assert get(db, watch) is None

    async def test_tap_during_push_keeps_tapped_message_and_interaction(
        self, db, bot, clock, watch
    ):
        make_live(db, watch, kind="empty", alerted=())
        gate = bot.gate("send_message")
        task = asyncio.create_task(apply(bot, watch, snap(Slot(D1, A))))
        await asyncio.sleep(0)

        tapped_at = clock.now = NOW + timedelta(seconds=5)
        await record_interaction(
            make_callback_update(cb.watch_stop(watch), USER, LIVE, bot=bot), None
        )
        gate.set()
        assert await task is AlertAction.PUSH

        assert await process_pending_retires(bot, NOW + timedelta(minutes=1)) == 0
        assert bot.edits == []
        [item] = all_queued(db)
        assert item.message_id == LIVE
        assert item.not_before == tapped_at + INTERACTION_LOCK
        rec = get(db, watch)
        assert rec.live.message_id == bot.sent[0].message_id
        assert rec.interacted_at == tapped_at

    async def test_book_tap_during_push_takes_over_tapped_message(
        self, db, bot, clock, watch
    ):
        make_live(db, watch, kind="empty", alerted=())
        gate = bot.gate("send_message")
        task = asyncio.create_task(apply(bot, watch, snap(Slot(D1, A))))
        await asyncio.sleep(0)

        clock.now = NOW + timedelta(seconds=5)
        await record_interaction(
            make_callback_update(cb.book_day(watch, D1), USER, LIVE, bot=bot), None
        )

        async def book_tap():
            async with alert_lock(watch):
                with Session(db) as session:
                    PendingRetireRepository(session).discard(USER, LIVE)
                book_session(db, message_id=LIVE)

        booking = asyncio.create_task(book_tap())
        await asyncio.sleep(0)
        gate.set()
        await task
        await booking

        await process_pending_retires(bot, NOW + timedelta(hours=1))
        assert bot.edits == []


class TestEndByChecker:
    async def test_deadline_finalizes_live_and_sends_silent_ended_message(
        self, db, bot, clock
    ):
        add_user(db)
        watch_id = add_watch(db, when=WhenSpec("before", date_to=NOW.date()))
        make_live(db, watch_id, Slot(D1, A))

        assert await end_watch_by_checker(bot, watch_id, "deadline", NOW)

        rec = get(db, watch_id)
        assert (rec.status, rec.end_reason) == ("ended", "deadline")
        [edit] = bot.edits
        assert edit.message_id == LIVE
        assert edit.text == render_final(rec, FinalState.DEADLINE, "en")
        assert edit.reply_markup is None
        [sent] = bot.sent
        expected = render_ended(rec, "en")
        assert sent.text == expected.text
        assert sent.reply_markup == expected.markup
        assert sent.disable_notification is True
        assert rec.live.message_id == sent.message_id
        assert rec.live.kind == "ended"
        assert rec.alerted == frozenset()
        assert cb.find_edit(watch_id) in str(sent.reply_markup.to_dict())

    async def test_gone_sends_gone_message_with_any_office(self, db, bot, clock):
        add_user(db, lang="ru")
        watch_id = add_watch(db, office_id=999)

        assert await end_watch_by_checker(bot, watch_id, "gone", NOW)

        rec = get(db, watch_id)
        assert (rec.status, rec.end_reason) == ("ended", "gone")
        [sent] = bot.sent
        assert sent.text == render_ended(rec, "ru").text
        assert cb.find_any(watch_id) in str(sent.reply_markup.to_dict())
        assert bot.edits == []

    async def test_live_alert_in_use_is_queued_not_edited(self, db, bot, clock):
        add_user(db)
        watch_id = add_watch(db, when=WhenSpec("before", date_to=NOW.date()))
        make_live(db, watch_id, Slot(D1, A))
        tapped_at = NOW - timedelta(minutes=2)
        tap(db, watch_id, tapped_at)

        await end_watch_by_checker(bot, watch_id, "deadline", NOW)

        assert bot.edits == []
        [item] = all_queued(db)
        assert item.message_id == LIVE
        assert item.not_before == tapped_at + INTERACTION_LOCK
        assert len(bot.sent) == 1

    async def test_paused_watch_ends_silently(self, db, bot, clock):
        add_user(db)
        watch_id = add_watch(db, when=WhenSpec("before", date_to=NOW.date()))
        with Session(db) as session:
            WatchRepository(session).set_status(watch_id, "paused", pause_reason="user")

        assert await end_watch_by_checker(bot, watch_id, "deadline", NOW)

        rec = get(db, watch_id)
        assert (rec.status, rec.end_reason) == ("ended", "deadline")
        assert rec.live is None
        assert bot.calls == []

    async def test_watch_reopened_before_the_end_stays_active(self, db, bot, clock):
        add_user(db)
        watch_id = add_watch(db, when=WhenSpec("before", date_to=NOW.date()))
        make_live(db, watch_id, Slot(D1, A))
        with Session(db) as session:
            WatchRepository(session).set_when(watch_id, PRESETS["asap"])

        assert not await end_watch_by_checker(bot, watch_id, "deadline", NOW)

        rec = get(db, watch_id)
        assert (rec.status, rec.end_reason) == ("active", None)
        assert rec.live.message_id == LIVE
        assert bot.calls == []

    async def test_watch_switched_to_public_office_stays_active(self, db, bot, clock):
        add_user(db)
        watch_id = add_watch(db, office_id=999)
        with Session(db) as session:
            WatchRepository(session).set_office(watch_id, None)

        assert not await end_watch_by_checker(bot, watch_id, "gone", NOW)

        assert get(db, watch_id).status == "active"
        assert bot.calls == []

    async def test_gone_when_every_office_was_rejected(self, db, bot, clock):
        add_user(db)
        rejected = add_watch(db, office_id=A)
        switched = add_watch(db, service_id=1063441, office_id=A)
        with Session(db) as session:
            WatchRepository(session).set_office(switched, B)

        assert await end_watch_by_checker(bot, rejected, "gone", NOW, frozenset({A}))
        assert not await end_watch_by_checker(
            bot, switched, "gone", NOW, frozenset({A})
        )

        assert get(db, rejected).end_reason == "gone"
        assert get(db, switched).status == "active"

    async def test_ended_or_missing_watch_is_left_alone(self, db, bot, watch):
        with Session(db) as session:
            WatchRepository(session).set_status(watch, "ended", end_reason="stopped")
        assert not await end_watch_by_checker(bot, watch, "deadline", NOW)
        assert not await end_watch_by_checker(bot, 999, "deadline", NOW)
        assert get(db, watch).end_reason == "stopped"
        assert bot.calls == []

    async def test_blocked_user_pauses_other_watches(self, db, bot, clock, events):
        events.patch(alert_lifecycle)
        add_user(db)
        watch_id = add_watch(db, when=WhenSpec("before", date_to=NOW.date()))
        other = add_watch(db, service_id=1063441)
        bot.fail_next("send_message", Forbidden("bot was blocked by the user"))

        assert await end_watch_by_checker(bot, watch_id, "deadline", NOW)

        assert get(db, watch_id).status == "ended"
        assert get(db, watch_id).live is None
        assert (get(db, other).status, get(db, other).pause_reason) == (
            "paused",
            "blocked",
        )
        assert [name for name, _ in events.calls] == ["user_blocked_bot"]


class TestCleanupExpiredBookings:
    async def test_expired_session_message_is_edited_and_session_deleted(
        self, db, bot, clock
    ):
        add_user(db, lang="ru")
        add_user(db, OTHER)
        book_session(db, expires_at=NOW - timedelta(seconds=1), message_id=77)
        book_session(db, OTHER, expires_at=NOW - timedelta(minutes=1))

        assert await cleanup_expired_bookings(bot) == 2

        [edit] = bot.edits
        assert (edit.chat_id, edit.message_id) == (USER, 77)
        assert edit.text == render_booking_timed_out("ru")
        assert edit.reply_markup is None
        with Session(db) as session:
            sessions = BookingSessionRepository(session)
            assert sessions.get_session(USER) is None
            assert sessions.get_session(OTHER) is None

    async def test_active_session_is_kept(self, db, bot, clock):
        add_user(db)
        book_session(db, expires_at=NOW + timedelta(minutes=1), message_id=77)
        assert await cleanup_expired_bookings(bot) == 0
        assert bot.calls == []
        with Session(db) as session:
            assert BookingSessionRepository(session).get_session(USER) is not None
