# ABOUTME: Tests for the check that runs right after a watch is created or its time is changed.
# ABOUTME: Availability is a scripted fake; Telegram is the recording FakeBot; DB is in-memory.

import asyncio
import html
from datetime import date

import pytest
from sqlmodel import Session
from telegram.error import BadRequest, Forbidden

from src.commands.find import find_command
from src.i18n import t
from src.repositories import MAX_OPEN_WATCHES, UserRepository, WatchRepository
from src.services import immediate_check
from src.services.immediate_check import (
    CHECKING_KEY,
    start_recheck,
    start_watch_check,
)
from src.ui import callbacks as cb
from src.watches.availability import ApiError, CallResult
from src.watches.labels import service_label, watch_summary
from src.watches.slots import Slot, SlotTime
from src.watches.when import PRESETS, WhenSpec
from tests.fakes import calendar, make_callback_update, make_text_update

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db", "catalog", "today", "clock"),
]

USER = 4242
MSG = 50
URGENT = 10339028
URGENT_OFFICE = 10461
ANMELDUNG = 1063475
FORSTENRIED = 102526
ORLEANS = 102522
DAY = date(2026, 10, 29)
TS = 1793260800
OTHER_SERVICES = (10339027, 10502137, 1063441, 1063453, 1071896, 1064305)


def register(db, lang="en"):
    with Session(db) as session:
        UserRepository(session).create_user(USER, language=lang)


def repo(db):
    return WatchRepository(Session(db))


def open_watch(db, service_id, office_id=None, when=PRESETS["asap"]):
    rec, _ = repo(db).create_or_update(USER, service_id, office_id, when)
    return rec


def nav_pointer(db):
    with Session(db) as session:
        return UserRepository(session).get_nav_message_id(USER)


def set_nav_pointer(db, message_id):
    with Session(db) as session:
        UserRepository(session).set_nav_message_id(USER, message_id)


def callback(context, message_id=MSG):
    return make_callback_update("f1:x", USER, message_id, bot=context.bot)


def slots_result(office=URGENT_OFFICE):
    return CallResult(
        True,
        calendar(days={"2026-10-29": [office]}, times={"2026-10-29": [(TS, office)]}),
        None,
    )


def empty_result():
    return CallResult(True, calendar(), None)


async def create(context, service_id=URGENT, office_id=None, when=PRESETS["asap"]):
    await start_watch_check(
        callback(context),
        context,
        USER,
        service_id,
        office_id,
        when,
        target_message_id=MSG,
    )


class TestCreate:
    async def test_handler_returns_before_the_check(
        self, db, context, fake_availability
    ):
        register(db)
        fake_availability.gate = asyncio.Event()
        fake_availability.calendar_results.append(slots_result())

        await create(context)
        await asyncio.sleep(0)

        assert [e.text for e in context.bot.edits] == [
            t("find.checking", "en", service=html.escape(service_label(URGENT, "en")))
        ]
        assert context.user_data[CHECKING_KEY] == MSG
        fake_availability.gate.set()
        await context.drain()
        assert len(context.bot.edits) == 2
        assert CHECKING_KEY not in context.user_data

    async def test_slots_become_the_live_alert(self, db, context, fake_availability):
        register(db)
        fake_availability.calendar_results.append(slots_result())
        await create(context)
        await context.drain()

        rec = repo(db).find_open(USER, URGENT)
        slots = frozenset({Slot(DAY, URGENT_OFFICE)})
        assert rec.live.chat_id == USER
        assert rec.live.message_id == MSG
        assert rec.live.kind == "slots"
        assert rec.live.shown == slots
        assert rec.alerted == slots
        assert rec.snapshot.slots == slots
        assert rec.snapshot.earliest_times == (SlotTime(TS, URGENT_OFFICE),)

        final = context.bot.edits[-1]
        assert final.message_id == MSG
        book = final.reply_markup.inline_keyboard[0][0]
        assert book.callback_data == cb.book_day(rec.id, DAY)

    async def test_no_slots(self, db, context, fake_availability):
        register(db, "ru")
        fake_availability.calendar_results.append(empty_result())
        await create(context)
        await context.drain()

        rec = repo(db).find_open(USER, URGENT)
        summary = html.escape(watch_summary(rec, "ru"))
        assert context.bot.edits[-1].text == t("alert.none_yet", "ru", summary=summary)
        assert context.bot.edits[-1].reply_markup is None
        assert rec.live.kind == "empty"
        assert rec.alerted == frozenset()
        assert rec.last_checked_at is not None

    async def test_check_failed(self, db, context, fake_availability):
        register(db)
        fake_availability.calendar_results.append(
            CallResult(False, None, ApiError.OTHER)
        )
        await create(context)
        await context.drain()

        rec = repo(db).find_open(USER, URGENT)
        summary = html.escape(watch_summary(rec, "en"))
        assert context.bot.edits[-1].text == t(
            "alert.check_failed", "en", summary=summary
        )
        assert rec.live.kind == "empty"
        assert rec.last_checked_at is None

    async def test_window_and_offices_of_the_watch(
        self, db, context, fake_availability, today
    ):
        register(db)
        fake_availability.calendar_results.append(empty_result())
        await create(context, ANMELDUNG, FORSTENRIED, WhenSpec("within", 14))
        await context.drain()
        service_id, offices, start, end, _ = fake_availability.calendar_calls[0]
        assert (service_id, offices) == (ANMELDUNG, [FORSTENRIED])
        assert (start, (end - start).days) == (today, 14)

    async def test_update_closes_previous_alert_as_outdated(
        self, db, context, fake_availability
    ):
        register(db)
        old = open_watch(db, ANMELDUNG, ORLEANS)
        shown = frozenset({Slot(DAY, ORLEANS)})
        repo(db).set_live_alert(old.id, USER, 30, "slots", shown, shown, "h")
        fake_availability.calendar_results.append(empty_result())

        await create(context, ANMELDUNG, None, PRESETS["1m"])
        await context.drain()

        assert [e.text for e in context.bot.edits if e.message_id == 30] == [
            t("alert.outdated", "en")
        ]
        rec = repo(db).get(old.id)
        assert rec.live.message_id == MSG
        assert context.bot.edits[-1].text.startswith(t("alert.updated_existing", "en"))

    async def test_nav_pointer_is_forgotten(self, db, context, fake_availability):
        register(db)
        set_nav_pointer(db, MSG)
        fake_availability.calendar_results.append(empty_result())
        await create(context)
        await context.drain()
        assert nav_pointer(db) is None

    async def test_nav_screen_during_the_check_never_strips_the_alert(
        self, db, context, fake_availability
    ):
        register(db)
        set_nav_pointer(db, MSG)
        fake_availability.calendar_results.append(slots_result())
        await create(context)
        final_edit = context.bot.gate("edit_message_text")
        await asyncio.sleep(0.01)

        await find_command(
            make_text_update("/find", USER, bot=context.bot, message_id=60), context
        )
        final_edit.set()
        await context.drain()

        strips = context.bot.calls_of("edit_message_reply_markup")
        assert MSG not in [c.message_id for c in strips]
        assert repo(db).find_open(USER, URGENT).live.message_id == MSG
        assert context.bot.edits[-1].message_id == MSG
        assert context.bot.edits[-1].reply_markup is not None

    async def test_new_alert_detaches_ended_alert_on_the_same_message(
        self, db, context, fake_availability
    ):
        register(db)
        ended = open_watch(db, ANMELDUNG)
        repo(db).set_status(ended.id, "ended", end_reason="deadline")
        repo(db).set_live_alert(
            ended.id, USER, MSG, "ended", frozenset(), frozenset(), "h"
        )
        fake_availability.calendar_results.append(slots_result())

        await create(context)
        await context.drain()

        assert repo(db).get(ended.id).live is None
        assert repo(db).find_open(USER, URGENT).live.message_id == MSG
        assert t("alert.outdated", "en") not in [e.text for e in context.bot.edits]

    async def test_limit_reached(self, db, context, fake_availability):
        register(db)
        set_nav_pointer(db, MSG)
        for sid in OTHER_SERVICES[:MAX_OPEN_WATCHES]:
            open_watch(db, sid)
        await create(context)
        await context.drain()

        final = context.bot.edits[-1]
        assert final.message_id == MSG
        assert final.text == t("find.limit", "en", count=MAX_OPEN_WATCHES)
        assert final.reply_markup.inline_keyboard[0][0].callback_data == (
            cb.watches_list()
        )
        assert repo(db).find_open(USER, URGENT) is None
        assert fake_availability.calendar_calls == []
        assert CHECKING_KEY not in context.user_data
        assert nav_pointer(db) == MSG

    async def test_deleted_alert_message_is_not_registered(
        self, db, context, fake_availability
    ):
        register(db)
        fake_availability.gate = asyncio.Event()
        fake_availability.calendar_results.append(slots_result())
        await create(context)
        await asyncio.sleep(0)
        context.bot.fail_next(
            "edit_message_text", BadRequest("Message to edit not found")
        )
        fake_availability.gate.set()
        await context.drain()
        assert repo(db).find_open(USER, URGENT).live is None

    async def test_blocked_user_pauses_watches(self, db, context, fake_availability):
        register(db)
        fake_availability.gate = asyncio.Event()
        fake_availability.calendar_results.append(slots_result())
        await create(context)
        await asyncio.sleep(0)
        context.bot.fail_next(
            "edit_message_text", Forbidden("bot was blocked by the user")
        )
        fake_availability.gate.set()
        await context.drain()
        rec = repo(db).find_open(USER, URGENT)
        assert (rec.status, rec.pause_reason, rec.live) == ("paused", "blocked", None)

    async def test_tracks_saved_watch(self, db, context, fake_availability, events):
        events.patch(immediate_check)
        register(db)
        fake_availability.calendar_results.append(empty_result())
        await create(context, when=PRESETS["2w"])
        await context.drain()
        assert events.calls == [
            (
                "watch_saved",
                {
                    "user_id": USER,
                    "service_id": URGENT,
                    "when_kind": "within",
                    "updated": False,
                },
            )
        ]


class TestTypedDatePath:
    async def test_new_message_below_the_text_becomes_live(
        self, db, context, fake_availability
    ):
        register(db)
        set_nav_pointer(db, 40)
        fake_availability.calendar_results.append(slots_result())
        update = make_text_update("15.11", USER, bot=context.bot, message_id=41)

        await start_watch_check(
            update,
            context,
            USER,
            URGENT,
            None,
            WhenSpec("before", date_to=date(2026, 11, 15)),
            target_message_id=None,
        )
        sent = context.bot.sent[-1]
        assert sent.text.startswith("🔎")
        assert context.user_data[CHECKING_KEY] == sent.message_id
        strips = context.bot.calls_of("edit_message_reply_markup")
        assert [c.message_id for c in strips] == [40]
        assert nav_pointer(db) is None

        await context.drain()
        rec = repo(db).find_open(USER, URGENT)
        assert rec.live.message_id == sent.message_id
        assert context.bot.edits[-1].message_id == sent.message_id


class TestRecheck:
    async def recheck(self, context, watch_id, when, target=MSG):
        await start_recheck(
            callback(context), context, watch_id, when, target_message_id=target
        )

    async def test_changes_time_and_checks(self, db, context, fake_availability):
        register(db)
        rec = open_watch(db, URGENT)
        fake_availability.calendar_results.append(slots_result())
        await self.recheck(context, rec.id, PRESETS["3m"])
        await context.drain()

        updated = repo(db).get(rec.id)
        assert updated.when == PRESETS["3m"]
        assert updated.live.message_id == MSG
        assert not context.bot.edits[-1].text.startswith(
            t("alert.updated_existing", "en")
        )

    async def test_previous_alert_closed_as_outdated(
        self, db, context, fake_availability
    ):
        register(db)
        rec = open_watch(db, URGENT)
        repo(db).set_live_alert(
            rec.id, USER, 30, "empty", frozenset(), frozenset(), "h"
        )
        fake_availability.calendar_results.append(empty_result())
        await self.recheck(context, rec.id, PRESETS["1m"])
        await context.drain()
        assert [e.text for e in context.bot.edits if e.message_id == 30] == [
            t("alert.outdated", "en")
        ]

    async def test_extend_on_the_ended_alert_reuses_it(
        self, db, context, fake_availability
    ):
        register(db)
        rec = open_watch(db, URGENT)
        repo(db).set_status(rec.id, "ended", end_reason="deadline")
        repo(db).set_live_alert(
            rec.id, USER, MSG, "ended", frozenset(), frozenset(), "h"
        )
        fake_availability.calendar_results.append(empty_result())
        await self.recheck(context, rec.id, PRESETS["asap"])
        await context.drain()

        updated = repo(db).get(rec.id)
        assert updated.status == "active"
        assert updated.live.message_id == MSG
        assert t("alert.outdated", "en") not in [e.text for e in context.bot.edits]

    async def test_reopen_redirect_to_open_watch(self, db, context, fake_availability):
        register(db)
        ended = open_watch(db, ANMELDUNG, FORSTENRIED)
        repo(db).set_status(ended.id, "ended", end_reason="deadline")
        repo(db).set_live_alert(
            ended.id, USER, 30, "ended", frozenset(), frozenset(), "h"
        )
        current = open_watch(db, ANMELDUNG, ORLEANS)
        repo(db).set_live_alert(
            current.id, USER, 31, "empty", frozenset(), frozenset(), "h"
        )
        fake_availability.calendar_results.append(empty_result())

        await self.recheck(context, ended.id, PRESETS["2w"])
        await context.drain()

        outdated = t("alert.outdated", "en")
        assert sorted(
            e.message_id for e in context.bot.edits if e.text == outdated
        ) == [
            30,
            31,
        ]
        assert repo(db).get(ended.id).live is None
        assert repo(db).get(ended.id).status == "ended"
        target = repo(db).get(current.id)
        assert (target.office_id, target.when) == (FORSTENRIED, PRESETS["2w"])
        assert target.live.message_id == MSG
        assert context.bot.edits[-1].text.startswith(t("alert.updated_existing", "en"))

    async def test_redirect_pressed_on_the_ended_alert_only_clears_it(
        self, db, context, fake_availability
    ):
        register(db)
        ended = open_watch(db, ANMELDUNG)
        repo(db).set_status(ended.id, "ended", end_reason="deadline")
        repo(db).set_live_alert(
            ended.id, USER, MSG, "ended", frozenset(), frozenset(), "h"
        )
        current = open_watch(db, ANMELDUNG)
        fake_availability.calendar_results.append(empty_result())

        await self.recheck(context, ended.id, PRESETS["asap"])
        await context.drain()

        assert t("alert.outdated", "en") not in [e.text for e in context.bot.edits]
        assert repo(db).get(ended.id).live is None
        assert repo(db).get(current.id).live.message_id == MSG

    async def test_reopen_at_limit(self, db, context, fake_availability):
        register(db)
        rec = open_watch(db, ANMELDUNG)
        repo(db).set_status(rec.id, "ended", end_reason="deadline")
        for sid in OTHER_SERVICES[:MAX_OPEN_WATCHES]:
            open_watch(db, sid)
        await self.recheck(context, rec.id, PRESETS["asap"])
        await context.drain()
        assert context.bot.edits[-1].text == t(
            "find.limit", "en", count=MAX_OPEN_WATCHES
        )
        assert repo(db).get(rec.id).status == "ended"

    async def test_unknown_watch_does_nothing(self, db, context, fake_availability):
        register(db)
        await self.recheck(context, 999, PRESETS["asap"])
        await context.drain()
        assert context.bot.calls == []


class TestCityCallHoldsNoLock:
    async def start_gated_recheck(self, db, context, fake_availability, rec):
        fake_availability.gate = asyncio.Event()
        fake_availability.calendar_results.append(slots_result())
        await start_recheck(
            callback(context), context, rec.id, PRESETS["2w"], target_message_id=MSG
        )
        while not fake_availability.calendar_calls:
            await asyncio.sleep(0)

    async def test_pause_during_the_check_does_not_wait_for_the_city(
        self, db, context, fake_availability
    ):
        from src.commands.watches import watches_callback

        register(db)
        rec = open_watch(db, URGENT)
        await self.start_gated_recheck(db, context, fake_availability, rec)

        pause = make_callback_update(cb.watch_pause(rec.id), USER, 60, bot=context.bot)
        await asyncio.wait_for(watches_callback(pause, context), timeout=1)
        assert repo(db).get(rec.id).status == "paused"

        fake_availability.gate.set()
        await context.drain()
        paused = repo(db).get(rec.id)
        assert paused.live is None
        assert [e.text for e in context.bot.edits if e.message_id == MSG][-1] == t(
            "alert.final_paused", "en", summary=html.escape(watch_summary(paused, "en"))
        )

    async def test_checker_leaves_the_watch_to_the_running_check(
        self, db, context, fake_availability, clock
    ):
        from src.services.alert_lifecycle import apply_alert
        from src.watches.alert_decision import AlertAction
        from src.watches.slots import WatchSnapshot

        register(db)
        rec = open_watch(db, URGENT)
        await self.start_gated_recheck(db, context, fake_availability, rec)

        checker_snapshot = WatchSnapshot(
            clock.now,
            True,
            frozenset({Slot(DAY, URGENT_OFFICE)}),
            (SlotTime(TS, URGENT_OFFICE),),
        )
        repo(db).record_check(rec.id, checker_snapshot)
        action = await asyncio.wait_for(
            apply_alert(
                context.bot, rec.id, checker_snapshot, clock.now, lambda _: False
            ),
            timeout=1,
        )
        assert action is AlertAction.NOOP
        assert context.bot.sent == []

        fake_availability.gate.set()
        await context.drain()
        assert repo(db).get(rec.id).live.message_id == MSG
