# ABOUTME: Tests for closing live alerts and the queue of messages waiting to lose their buttons.
# ABOUTME: Real DB (in-memory), recording FakeBot, fixed clock.

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session
from telegram.error import BadRequest, Forbidden, NetworkError

from src.i18n import t
from src.repositories import (
    BookingSessionRepository,
    PendingRetireRepository,
    UserRepository,
    WatchRepository,
)
from src.watches.alert_ops import (
    alert_lock,
    close_live_alert,
    process_pending_retires,
    queue_retire,
)
from src.watches.alert_view import FinalState, render_final
from src.watches.slots import Slot
from src.watches.when import PRESETS
from tests.fakes import FakeBot

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("catalog")]

USER = 4242
LIVE_MSG = 500
SHOWN = frozenset({Slot(datetime(2026, 10, 29).date(), 102526)})


@pytest.fixture
def watch_id(db):
    with Session(db) as session:
        UserRepository(session).create_user(USER, language="en")
        rec, _ = WatchRepository(session).create_or_update(
            USER, 1063475, None, PRESETS["asap"]
        )
        WatchRepository(session).set_live_alert(
            rec.id, USER, LIVE_MSG, "slots", SHOWN, SHOWN, "h"
        )
        return rec.id


def get(db, watch_id):
    with Session(db) as session:
        return WatchRepository(session).get(watch_id)


def queued(db, now):
    with Session(db) as session:
        return PendingRetireRepository(session).due(now)


def tap(db, at):
    with Session(db) as session:
        WatchRepository(session).mark_interaction(USER, LIVE_MSG, at)


def start_booking(db, message_id, expires_at):
    with Session(db) as session:
        BookingSessionRepository(session).create_session(
            USER,
            "SELECTING_TIME",
            1063475,
            0,
            "2026-10-29",
            "",
            expires_at,
            message_id=message_id,
        )


class TestAlertLock:
    async def test_per_watch(self):
        assert alert_lock(1) is alert_lock(1)
        assert alert_lock(1) is not alert_lock(2)


class TestCloseByUser:
    async def test_edits_final_text_and_clears(self, db, clock, watch_id):
        bot = FakeBot()
        rec = get(db, watch_id)
        async with alert_lock(watch_id):
            await close_live_alert(
                bot, watch_id, FinalState.STOPPED, "en", by_user=True
            )

        [edit] = bot.edits
        assert (edit.chat_id, edit.message_id) == (USER, LIVE_MSG)
        assert edit.text == render_final(rec, FinalState.STOPPED, "en")
        assert edit.reply_markup is None
        after = get(db, watch_id)
        assert after.live is None and after.alerted == frozenset()
        assert queued(db, clock.now + timedelta(days=1)) == []

    @pytest.mark.parametrize(
        "exc",
        [
            BadRequest("Message to edit not found"),
            BadRequest("Message is not modified"),
        ],
    )
    async def test_gone_or_not_modified_needs_nothing_more(
        self, db, clock, watch_id, exc
    ):
        bot = FakeBot()
        bot.fail_next("edit_message_text", exc)
        await close_live_alert(bot, watch_id, FinalState.PAUSED, "en", by_user=True)
        assert get(db, watch_id).live is None
        assert queued(db, clock.now) == []

    async def test_failure_is_queued_now(self, db, clock, watch_id):
        bot = FakeBot()
        bot.fail_next("edit_message_text", NetworkError("down"))
        await close_live_alert(bot, watch_id, FinalState.BOOKED, "ru", by_user=True)

        [item] = queued(db, clock.now)
        assert (item.chat_id, item.message_id) == (USER, LIVE_MSG)
        assert item.text.startswith("✅ <b>Вы записаны</b>")
        assert get(db, watch_id).live is None

    async def test_reopen_redirect_leaves_pressed_alert_for_caller_to_close(
        self, db, clock, watch_id
    ):
        with Session(db) as session:
            watches = WatchRepository(session)
            watches.clear_live_alert(watch_id, reset_alerted=True)
            watches.set_status(watch_id, "ended", end_reason="deadline")
            watches.set_live_alert(
                watch_id, USER, LIVE_MSG, "ended", frozenset(), frozenset(), "h"
            )
            current, _ = watches.create_or_update(USER, 1063475, 10489, PRESETS["asap"])
            reopened = watches.set_when(watch_id, PRESETS["1m"])
        assert reopened.id == current.id != watch_id

        bot = FakeBot()
        async with alert_lock(watch_id):
            await close_live_alert(
                bot, watch_id, FinalState.OUTDATED, "en", by_user=True
            )

        [edit] = bot.edits
        assert (edit.message_id, edit.text) == (LIVE_MSG, t("alert.outdated", "en"))
        assert edit.reply_markup is None
        assert get(db, watch_id).live is None

    async def test_outdated_text(self, db, clock, watch_id):
        bot = FakeBot()
        await close_live_alert(bot, watch_id, FinalState.OUTDATED, "en", by_user=True)
        assert bot.edits[0].text == t("alert.outdated", "en")

    async def test_no_live_alert_is_noop(self, db, clock, watch_id):
        bot = FakeBot()
        with Session(db) as session:
            WatchRepository(session).clear_live_alert(watch_id, reset_alerted=False)
        await close_live_alert(bot, watch_id, FinalState.STOPPED, "en", by_user=True)
        await close_live_alert(bot, 9999, FinalState.STOPPED, "en", by_user=True)
        assert bot.calls == []


class TestCloseByChecker:
    async def test_idle_message_is_edited_now(self, db, clock, watch_id):
        bot = FakeBot()
        await close_live_alert(bot, watch_id, FinalState.DEADLINE, "en", by_user=False)
        assert bot.edits[0].text.startswith("⌛ <b>Watch ended</b>")
        assert get(db, watch_id).live is None

    async def test_recent_tap_queues_until_lock_ends(self, db, clock, watch_id):
        bot = FakeBot()
        tapped = clock.now - timedelta(minutes=3)
        tap(db, tapped)

        await close_live_alert(bot, watch_id, FinalState.GONE, "en", by_user=False)

        assert bot.edits == []
        assert queued(db, clock.now + timedelta(minutes=6)) == []
        [item] = queued(db, tapped + timedelta(minutes=10))
        assert item.text.startswith("⚠️ <b>Watch ended</b>")
        assert get(db, watch_id).live is None

    async def test_old_tap_does_not_block(self, db, clock, watch_id):
        bot = FakeBot()
        tap(db, clock.now - timedelta(minutes=10))
        await close_live_alert(bot, watch_id, FinalState.DEADLINE, "en", by_user=False)
        assert len(bot.edits) == 1

    async def test_booking_session_queues_until_it_expires(self, db, clock, watch_id):
        bot = FakeBot()
        expires = clock.now + timedelta(minutes=12)
        start_booking(db, LIVE_MSG, expires)

        await close_live_alert(bot, watch_id, FinalState.DEADLINE, "en", by_user=False)

        assert bot.edits == []
        [item] = queued(db, expires)
        assert item.not_before == expires

    async def test_failed_edit_is_queued(self, db, clock, watch_id):
        bot = FakeBot()
        bot.fail_next("edit_message_text", NetworkError("down"))
        await close_live_alert(bot, watch_id, FinalState.DEADLINE, "en", by_user=False)
        assert len(queued(db, clock.now)) == 1


class TestPendingRetires:
    async def test_due_and_not_due(self, db, clock):
        bot = FakeBot()
        queue_retire(USER, USER, 1, "old 1", clock.now)
        queue_retire(USER, USER, 2, "old 2", clock.now + timedelta(minutes=5))

        assert await process_pending_retires(bot, clock.now) == 1
        assert [(e.message_id, e.text, e.reply_markup) for e in bot.edits] == [
            (1, "old 1", None)
        ]
        assert [i.message_id for i in queued(db, clock.now + timedelta(minutes=5))] == [
            2
        ]

    async def test_message_in_booking_is_rescheduled(self, db, clock):
        bot = FakeBot()
        with Session(db) as session:
            UserRepository(session).create_user(USER)
        expires = clock.now + timedelta(minutes=10)
        start_booking(db, 7, expires)
        queue_retire(USER, USER, 7, "outdated", clock.now)

        assert await process_pending_retires(bot, clock.now) == 0

        assert bot.edits == []
        [item] = queued(db, expires)
        assert item.not_before == expires

    async def test_tap_postpones(self, db, clock):
        bot = FakeBot()
        queue_retire(USER, USER, 7, "outdated", clock.now)
        with Session(db) as session:
            PendingRetireRepository(session).touch(
                USER, 7, clock.now + timedelta(minutes=10)
            )
        await process_pending_retires(bot, clock.now)
        assert bot.edits == []

    @pytest.mark.parametrize(
        "exc",
        [
            BadRequest("Message is not modified"),
            BadRequest("Message to edit not found"),
            Forbidden("bot was blocked by the user"),
        ],
    )
    async def test_final_outcomes_drop_the_row(self, db, clock, exc):
        bot = FakeBot()
        bot.fail_next("edit_message_text", exc)
        queue_retire(USER, USER, 7, "outdated", clock.now)
        await process_pending_retires(bot, clock.now)
        assert queued(db, clock.now + timedelta(days=1)) == []

    async def test_failure_backs_off_then_succeeds(self, db, clock):
        bot = FakeBot()
        bot.fail_next("edit_message_text", NetworkError("flood"))
        queue_retire(USER, USER, 7, "outdated", clock.now)

        assert await process_pending_retires(bot, clock.now) == 0
        [item] = queued(db, clock.now + timedelta(minutes=2))
        assert item.attempts == 1
        assert queued(db, clock.now + timedelta(minutes=1)) == []

        assert await process_pending_retires(bot, clock.now + timedelta(minutes=2)) == 1
        assert bot.edits[-1].text == "outdated"
        assert queued(db, clock.now + timedelta(days=1)) == []

    async def _retire_two_while(self, db, clock, change) -> FakeBot:
        """Runs the queue for messages 10 and 20; `change` runs while the edit of 10 is held."""
        with Session(db) as session:
            UserRepository(session).create_user(USER)
        bot = FakeBot()
        queue_retire(USER, USER, 10, "outdated 10", clock.now)
        queue_retire(USER, USER, 20, "outdated 20", clock.now)
        gate = bot.gate("edit_message_text")
        task = asyncio.create_task(process_pending_retires(bot, clock.now))
        for _ in range(5):
            await asyncio.sleep(0)
        change()
        gate.set()
        await task
        return bot

    async def test_row_discarded_during_the_run_is_not_edited(self, db, clock):
        def book_tap():
            with Session(db) as session:
                PendingRetireRepository(session).discard(USER, 20)

        bot = await self._retire_two_while(db, clock, book_tap)
        assert [e.message_id for e in bot.edits] == [10]

    async def test_row_tapped_during_the_run_is_not_edited(self, db, clock):
        later = clock.now + timedelta(minutes=10)

        def tap_queued():
            with Session(db) as session:
                PendingRetireRepository(session).touch(USER, 20, later)

        bot = await self._retire_two_while(db, clock, tap_queued)
        assert [e.message_id for e in bot.edits] == [10]
        [item] = queued(db, later)
        assert item.message_id == 20

    async def test_booking_started_during_the_run_reschedules(self, db, clock):
        expires = clock.now + timedelta(minutes=15)
        bot = await self._retire_two_while(
            db, clock, lambda: start_booking(db, 20, expires)
        )
        assert [e.message_id for e in bot.edits] == [10]
        [item] = queued(db, expires)
        assert item.message_id == 20 and item.not_before == expires

    async def test_attempts_cap(self, db, clock, caplog):
        bot = FakeBot()
        queue_retire(USER, USER, 7, "outdated", clock.now)
        now = clock.now
        for _ in range(6):
            bot.fail_next("edit_message_text", NetworkError("down"))
            await process_pending_retires(bot, now)
            now += timedelta(days=1)
        assert queued(db, now) == []
        assert any("gave up" in r.getMessage() for r in caplog.records)
