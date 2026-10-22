# ABOUTME: Tests for booking from a watch's alert: detaching the alert, fetching times, ending the
# ABOUTME: watch after a booking, stale buttons and restart cleanup. Real DB, FakeBot, faked city API.

import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session
from telegram.ext import ApplicationHandlerStop, ConversationHandler

from src.commands import booking
from src.i18n import t
from src.munich_api_client import ApiResponse
from src.repositories import (
    BookingSessionRepository,
    PendingRetireRepository,
    UserRepository,
    WatchRepository,
)
from src.watches import availability
from src.watches.alert_decision import AlertAction, decide_alert, interaction_state
from src.watches.alert_view import FinalState, render_final
from src.watches.slots import Slot, SlotTime
from src.watches.when import PRESETS
from tests.conftest import BUERGERBUERO, NOW
from tests.fakes import FakeBot, FakeContext, make_callback_update

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("catalog", "clock", "today")]

USER = 4242
OTHER_USER = 777
WOHNSITZ = 1063475
FUEHRERSCHEIN = 1071896
FUEHRERSCHEIN_OFFICE = 10308174
FORSTENRIEDER = 102526
ORLEANSPLATZ = 102522
LIVE_MSG = 500
OLD_MSG = 400
DAY = date(2026, 10, 29)
BERLIN = ZoneInfo("Europe/Berlin")
SHOWN = frozenset({Slot(DAY, FORSTENRIEDER), Slot(date(2026, 11, 3), ORLEANSPLATZ)})
NAME = "Ivan Petrov"
EMAIL = "ivan@example.com"


def ts(hour: int, minute: int = 0, day: date = DAY) -> int:
    return int(
        datetime(day.year, day.month, day.day, hour, minute, tzinfo=BERLIN).timestamp()
    )


@pytest.fixture
def bot():
    return FakeBot()


@pytest.fixture
def context(bot):
    return FakeContext(bot)


@pytest.fixture
def stats(monkeypatch):
    counts = {"started": 0, "completed": 0}

    def started():
        counts["started"] += 1

    def completed():
        counts["completed"] += 1

    monkeypatch.setattr(booking, "increment_bookings_started", started)
    monkeypatch.setattr(booking, "increment_bookings_completed", completed)
    return counts


@pytest.fixture(autouse=True)
def quiet_events(events):
    events.patch(booking)
    return events


@pytest.fixture
def user(db):
    with Session(db) as session:
        UserRepository(session).create_user(USER, username="tester", language="en")
    return USER


def make_watch(db, service_id=WOHNSITZ, office_id=None, *, live=True, user_id=USER):
    with Session(db) as session:
        watches = WatchRepository(session)
        rec, _ = watches.create_or_update(
            user_id, service_id, office_id, PRESETS["asap"]
        )
        if live:
            watches.set_live_alert(
                rec.id, user_id, LIVE_MSG, "slots", SHOWN, SHOWN, "hash"
            )
        return rec.id


def get_watch(db, watch_id):
    with Session(db) as session:
        return WatchRepository(session).get(watch_id)


def get_booking(db, user_id=USER):
    with Session(db) as session:
        row = BookingSessionRepository(session).get_session(user_id)
        return (
            None
            if row is None
            else (
                row.watch_id,
                row.office_id,
                row.message_id,
                row.date,
                row.captcha_token,
                row.state,
            )
        )


def book_data(watch_id, day=DAY):
    return f"b1:{watch_id}:{day.strftime('%Y%m%d')}"


async def tap(handler, context, data, message_id=LIVE_MSG, user_id=USER):
    """Run a conversation callback; returns the state it hands to the conversation"""
    update = make_callback_update(data, user_id, message_id, bot=context.bot)
    try:
        return await handler(update, context)
    except ApplicationHandlerStop as stop:
        return ("stop", stop.state)


def edits_of(bot, message_id):
    return [c for c in bot.edits if c.message_id == message_id]


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def answers(bot):
    return [c.text for c in bot.calls_of("answer_callback_query")]


class GatedDayTimes:
    """Holds fetch_day_times until released, to show the handler does not wait for it"""

    def __init__(self, monkeypatch, fake_availability):
        self.release = asyncio.Event()
        self.fake = fake_availability
        monkeypatch.setattr(availability, "fetch_day_times", self)

    async def __call__(self, service_id, office_ids, day):
        await self.release.wait()
        return await self.fake.fetch_day_times(service_id, office_ids, day)


class TestBookTapOnLiveAlert:
    async def test_returns_before_times_arrive_then_shows_them(
        self, db, user, context, bot, monkeypatch, fake_availability, stats
    ):
        watch_id = make_watch(db)
        gated = GatedDayTimes(monkeypatch, fake_availability)
        fake_availability.day_results = [
            (SlotTime(ts(9), FORSTENRIEDER), SlotTime(ts(9, 5), ORLEANSPLATZ))
        ]

        state = await tap(booking.book_day, context, book_data(watch_id))

        assert state == ("stop", booking.SELECTING_TIME)
        [fetching] = edits_of(bot, LIVE_MSG)
        assert fetching.text == t("booking.fetching_slots", "en", date="Thu 29.10")
        assert fetching.reply_markup is None
        assert stats["started"] == 0

        gated.release.set()
        await context.drain()

        assert fake_availability.day_calls == [(WOHNSITZ, sorted(BUERGERBUERO), DAY)]
        times = edits_of(bot, LIVE_MSG)[-1]
        assert times.text == t("booking.select_time", "en", date="Thu 29.10")
        assert buttons(times.reply_markup) == [
            ("09:00 · Forstenrieder Allee", f"b1:t:{FORSTENRIEDER}:{ts(9)}"),
            ("09:05 · Orleansplatz", f"b1:t:{ORLEANSPLATZ}:{ts(9, 5)}"),
            ("❌ Cancel", "b1:x"),
        ]
        assert stats["started"] == 1

    async def test_detaches_the_alert_under_the_lock(
        self, db, user, context, fake_availability
    ):
        watch_id = make_watch(db)
        with Session(db) as session:
            WatchRepository(session).mark_interaction(USER, LIVE_MSG, NOW)
        fake_availability.day_results = [(SlotTime(ts(9), FORSTENRIEDER),)]

        await tap(booking.book_day, context, book_data(watch_id))

        rec = get_watch(db, watch_id)
        assert rec.live is None
        assert rec.alerted == frozenset()
        assert rec.interacted_at is None
        assert rec.status == "active"
        assert get_booking(db) == (
            watch_id,
            0,
            LIVE_MSG,
            "2026-10-29",
            "",
            "SELECTING_TIME",
        )
        await context.drain()

    async def test_waits_for_a_running_alert_update_before_detaching(
        self, db, user, context, fake_availability
    ):
        watch_id = make_watch(db)
        fake_availability.day_results = [(SlotTime(ts(9), FORSTENRIEDER),)]
        lock = booking.alert_lock(watch_id)
        await lock.acquire()

        task = asyncio.create_task(tap(booking.book_day, context, book_data(watch_id)))
        await asyncio.sleep(0.01)
        assert not task.done()
        assert get_watch(db, watch_id).live is not None

        lock.release()
        assert await task == ("stop", booking.SELECTING_TIME)
        assert get_watch(db, watch_id).live is None
        await context.drain()

    async def test_session_defers_alerts_until_cancel_then_alert_is_sent_again(
        self, db, user, context, clock, fake_availability
    ):
        watch_id = make_watch(db)
        fake_availability.day_results = [(SlotTime(ts(9), FORSTENRIEDER),)]
        await tap(booking.book_day, context, book_data(watch_id))
        await context.drain()

        with Session(db) as session:
            assert BookingSessionRepository(session).is_user_in_booking(USER)
            rec = WatchRepository(session).get(watch_id)
        during = interaction_state(True, rec.interacted_at, clock.now)
        assert (
            decide_alert(rec.alerted, SHOWN, None, frozenset(), False, during).action
            is AlertAction.DEFER
        )

        clock.now += timedelta(minutes=1)
        await tap(booking.cancel, context, "b1:x")

        with Session(db) as session:
            assert not BookingSessionRepository(session).is_user_in_booking(USER)
            rec = WatchRepository(session).get(watch_id)
        after = interaction_state(False, rec.interacted_at, clock.now)
        live_kind = rec.live.kind if rec.live else None
        assert (
            decide_alert(
                rec.alerted, SHOWN, live_kind, frozenset(), False, after
            ).action
            is AlertAction.PUSH
        )

    async def test_single_office_watch_times_have_no_office_label(
        self, db, user, context, bot, fake_availability
    ):
        watch_id = make_watch(db, FUEHRERSCHEIN, FUEHRERSCHEIN_OFFICE)
        fake_availability.day_results = [
            (
                SlotTime(ts(8), FUEHRERSCHEIN_OFFICE),
                SlotTime(ts(8, 30), FUEHRERSCHEIN_OFFICE),
            )
        ]

        await tap(booking.book_day, context, book_data(watch_id))
        await context.drain()

        assert fake_availability.day_calls == [
            (FUEHRERSCHEIN, [FUEHRERSCHEIN_OFFICE], DAY)
        ]
        assert get_booking(db)[1] == FUEHRERSCHEIN_OFFICE
        assert buttons(edits_of(bot, LIVE_MSG)[-1].reply_markup)[:2] == [
            ("08:00", f"b1:t:{FUEHRERSCHEIN_OFFICE}:{ts(8)}"),
            ("08:30", f"b1:t:{FUEHRERSCHEIN_OFFICE}:{ts(8, 30)}"),
        ]

    async def test_times_are_fetched_with_a_token_solved_for_this_tap(
        self, db, user, context, bot, fake_api, fake_token
    ):
        watch_id = make_watch(db, FUEHRERSCHEIN, FUEHRERSCHEIN_OFFICE)
        fake_api["get"] = [
            ApiResponse(
                {
                    "availableDays": [
                        {
                            "date": "2026-10-29",
                            "providerIDs": str(FUEHRERSCHEIN_OFFICE),
                            "offices": [
                                {
                                    "officeId": str(FUEHRERSCHEIN_OFFICE),
                                    "appointments": [ts(8)],
                                }
                            ],
                        }
                    ]
                },
                200,
                (),
            )
        ]

        await tap(booking.book_day, context, book_data(watch_id))
        assert fake_token["issued"] == 0
        await context.drain()

        [(_, endpoint, params)] = fake_api["calls"]
        assert endpoint == "available-calendar/"
        assert params["captchaToken"] == "token-1"
        assert params["slotsStartDate"] == params["slotsEndDate"] == "2026-10-29"
        assert buttons(edits_of(bot, LIVE_MSG)[-1].reply_markup)[0] == (
            "08:00",
            f"b1:t:{FUEHRERSCHEIN_OFFICE}:{ts(8)}",
        )


class TestBookTapEdgeCases:
    async def test_tap_on_queued_message_discards_its_retire(
        self, db, user, context, bot, clock, fake_availability
    ):
        watch_id = make_watch(db)
        with Session(db) as session:
            PendingRetireRepository(session).add(USER, USER, OLD_MSG, "outdated", NOW)
        fake_availability.day_results = [(SlotTime(ts(9), FORSTENRIEDER),)]

        await tap(booking.book_day, context, book_data(watch_id), message_id=OLD_MSG)
        await context.drain()

        with Session(db) as session:
            assert (
                PendingRetireRepository(session).due(clock.now + timedelta(days=1))
                == []
            )
        rec = get_watch(db, watch_id)
        assert rec.live is not None and rec.live.message_id == LIVE_MSG
        assert rec.alerted == SHOWN
        assert edits_of(bot, LIVE_MSG) == []
        assert get_booking(db)[2] == OLD_MSG

    @pytest.mark.parametrize("status", ["ended", "missing", "other_user"])
    async def test_watch_not_open_gives_a_toast(self, db, user, context, bot, status):
        if status == "other_user":
            with Session(db) as session:
                UserRepository(session).create_user(OTHER_USER, language="en")
            watch_id = make_watch(db, user_id=OTHER_USER, live=False)
        elif status == "missing":
            watch_id = 999
        else:
            watch_id = make_watch(db)
            with Session(db) as session:
                WatchRepository(session).set_status(
                    watch_id, "ended", end_reason="stopped"
                )

        state = await tap(booking.book_day, context, book_data(watch_id))

        assert state == ("stop", None)
        assert answers(bot) == [t("booking.watch_ended", "en")]
        assert bot.edits == []
        assert get_booking(db) is None
        assert context.application.tasks == []

    async def test_toast_leaves_a_running_booking_alone(self, db, user, context, bot):
        open_confirming_session(db, None, message_id=OLD_MSG)

        state = await tap(booking.book_day, context, book_data(999))

        assert state == ("stop", None)
        assert get_booking(db)[2] == OLD_MSG

    async def test_paused_watch_can_still_book(
        self, db, user, context, fake_availability
    ):
        watch_id = make_watch(db)
        with Session(db) as session:
            WatchRepository(session).set_status(watch_id, "paused", pause_reason="user")
        fake_availability.day_results = [(SlotTime(ts(9), FORSTENRIEDER),)]

        state = await tap(booking.book_day, context, book_data(watch_id))
        await context.drain()

        assert state == ("stop", booking.SELECTING_TIME)

    @pytest.mark.parametrize(
        ("result", "key"), [((), "booking.day_gone"), (None, "booking.times_failed")]
    )
    async def test_no_times_ends_the_session(
        self, db, user, context, bot, fake_availability, stats, result, key
    ):
        watch_id = make_watch(db)
        fake_availability.day_results = [result]

        await tap(booking.book_day, context, book_data(watch_id))
        await context.drain()

        last = edits_of(bot, LIVE_MSG)[-1]
        assert last.text == (
            t(key, "en", date="Thu 29.10") + "\n\n" + t("booking.will_send_days", "en")
        )
        assert last.reply_markup is None
        assert get_booking(db) is None
        assert stats["started"] == 0

    async def test_past_day_is_gone_without_asking_the_city(
        self, db, user, context, bot, fake_availability
    ):
        watch_id = make_watch(db)

        await tap(booking.book_day, context, book_data(watch_id, date(2026, 10, 20)))
        await context.drain()

        assert fake_availability.day_calls == []
        assert edits_of(bot, LIVE_MSG)[-1].text == (
            t("booking.day_gone", "en", date="Tue 20.10")
            + "\n\n"
            + t("booking.will_send_days", "en")
        )

    async def test_no_times_for_a_paused_watch_promises_nothing(
        self, db, user, context, bot, fake_availability
    ):
        watch_id = make_watch(db)
        with Session(db) as session:
            WatchRepository(session).set_status(watch_id, "paused", pause_reason="user")
        fake_availability.day_results = [()]

        await tap(booking.book_day, context, book_data(watch_id))
        await context.drain()

        assert edits_of(bot, LIVE_MSG)[-1].text == t(
            "booking.day_gone", "en", date="Thu 29.10"
        )

    async def test_double_tap_fetches_once(self, db, user, context, fake_availability):
        watch_id = make_watch(db)
        fake_availability.day_results = [(SlotTime(ts(9), FORSTENRIEDER),)]

        first = await tap(booking.book_day, context, book_data(watch_id))
        second = await tap(booking.book_day, context, book_data(watch_id))
        await context.drain()

        assert first == ("stop", booking.SELECTING_TIME)
        assert second == ("stop", None)
        assert len(fake_availability.day_calls) == 1

    async def test_new_book_tap_strips_the_previous_booking_message(
        self, db, user, context, bot, fake_availability
    ):
        first_watch = make_watch(db)
        second_watch = make_watch(db, FUEHRERSCHEIN, FUEHRERSCHEIN_OFFICE, live=False)
        fake_availability.day_results = [
            (SlotTime(ts(9), FORSTENRIEDER),),
            (SlotTime(ts(8), FUEHRERSCHEIN_OFFICE),),
        ]
        await tap(booking.book_day, context, book_data(first_watch))
        await context.drain()

        await tap(
            booking.book_day, context, book_data(second_watch), message_id=OLD_MSG
        )
        await context.drain()

        stripped = bot.calls_of("edit_message_reply_markup")
        assert [(c.message_id, c.reply_markup) for c in stripped] == [(LIVE_MSG, None)]
        assert get_booking(db)[:3] == (second_watch, FUEHRERSCHEIN_OFFICE, OLD_MSG)

    async def test_cancel_while_times_load_leaves_the_message_alone(
        self, db, user, context, bot, monkeypatch, fake_availability
    ):
        watch_id = make_watch(db)
        gated = GatedDayTimes(monkeypatch, fake_availability)
        fake_availability.day_results = [(SlotTime(ts(9), FORSTENRIEDER),)]
        await tap(booking.book_day, context, book_data(watch_id))

        await booking.leave_booking(
            make_callback_update("w1:list", USER, 900, bot=bot), context
        )
        gated.release.set()
        await context.drain()

        assert [e.text for e in edits_of(bot, LIVE_MSG)] == [
            t("booking.fetching_slots", "en", date="Thu 29.10")
        ]

    async def test_replaced_booking_does_not_get_the_old_times(
        self, db, user, context, bot, monkeypatch, fake_availability
    ):
        first = make_watch(db)
        second = make_watch(db, FUEHRERSCHEIN, FUEHRERSCHEIN_OFFICE, live=False)
        gated = GatedDayTimes(monkeypatch, fake_availability)
        fake_availability.day_results = [
            (SlotTime(ts(9), FORSTENRIEDER),),
            (SlotTime(ts(8), FUEHRERSCHEIN_OFFICE),),
        ]
        await tap(booking.book_day, context, book_data(first))
        await tap(booking.book_day, context, book_data(second), message_id=OLD_MSG)

        gated.release.set()
        await context.drain()

        assert [e.text for e in edits_of(bot, LIVE_MSG)] == [
            t("booking.fetching_slots", "en", date="Thu 29.10")
        ]
        assert edits_of(bot, OLD_MSG)[-1].text == t(
            "booking.select_time", "en", date="Thu 29.10"
        )


class TestLegacyBookButton:
    async def test_books_the_office_of_the_button_without_a_watch(
        self, db, user, context, bot, fake_availability
    ):
        fake_availability.day_results = [(SlotTime(ts(10), 10461),)]

        state = await tap(
            booking.book_legacy, context, "book_2026-10-29_10461_10339028", OLD_MSG
        )
        await context.drain()

        assert state == ("stop", booking.SELECTING_TIME)
        assert fake_availability.day_calls == [(10339028, [10461], DAY)]
        assert get_booking(db)[:3] == (None, 10461, OLD_MSG)
        assert buttons(edits_of(bot, OLD_MSG)[-1].reply_markup)[0] == (
            "10:00",
            f"b1:t:10461:{ts(10)}",
        )

    async def test_impossible_date_gives_a_toast(self, db, user, context, bot):
        state = await tap(
            booking.book_legacy, context, "book_2026-02-31_10461_10339028", OLD_MSG
        )

        assert state == ("stop", None)
        assert answers(bot) == [t("booking.invalid_data", "en")]
        assert get_booking(db) is None


def open_confirming_session(
    db, watch_id, message_id=LIVE_MSG, office_id=FORSTENRIEDER, expires_in=15
):
    with Session(db) as session:
        repo = BookingSessionRepository(session)
        repo.create_session(
            user_id=USER,
            state="CONFIRMING",
            service_id=WOHNSITZ,
            office_id=office_id,
            date=DAY.isoformat(),
            captcha_token="",
            expires_at=NOW + timedelta(minutes=expires_in),
            watch_id=watch_id,
            message_id=message_id,
        )
        repo.update_session(USER, timestamp=ts(9), name=NAME, email=EMAIL)


@pytest.fixture
def city(monkeypatch):
    """Scripted booking_api.book_appointment results (an Event holds the call until set, then
    fails it); records the calls"""
    state = {"results": [], "calls": []}

    async def book_appointment(**kwargs):
        state["calls"].append(kwargs)
        result = state["results"].pop(0)
        if isinstance(result, asyncio.Event):
            await result.wait()
            return None
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(booking.booking_api, "book_appointment", book_appointment)
    return state


class TestBookingResult:
    async def test_success_ends_the_watch_and_saves_the_contact(
        self, db, user, context, bot, city, stats
    ):
        watch_id = make_watch(db, live=False)
        open_confirming_session(db, watch_id)
        city["results"] = [{"processId": "P-42"}]

        state = await tap(booking.confirm, context, "b1:ok")
        assert state == ("stop", ConversationHandler.END)
        await context.drain()

        assert city["calls"] == [
            {
                "timestamp": ts(9),
                "office_id": FORSTENRIEDER,
                "service_id": WOHNSITZ,
                "service_name": "Wohnsitzanmeldung",
                "family_name": NAME,
                "email": EMAIL,
            }
        ]
        rec = get_watch(db, watch_id)
        assert (rec.status, rec.end_reason) == ("ended", "booked")
        with Session(db) as session:
            assert UserRepository(session).get_booking_contact(USER) == (NAME, EMAIL)
        assert get_booking(db) is None
        assert stats["completed"] == 1
        final = edits_of(bot, LIVE_MSG)[-1]
        assert final.text.endswith(
            "\n\n"
            + t(
                "booking.watch_finished",
                "en",
                service="Address registration (Anmeldung)",
            )
        )
        # Kept as the booking confirmation: no button that would replace it in place
        assert final.reply_markup is None

    async def test_success_closes_a_newer_live_alert_as_booked(
        self, db, user, context, bot, city
    ):
        watch_id = make_watch(db)
        open_confirming_session(db, watch_id, message_id=OLD_MSG)
        city["results"] = [{"processId": "P-42"}]

        await tap(booking.confirm, context, "b1:ok", message_id=OLD_MSG)
        await context.drain()

        rec = get_watch(db, watch_id)
        assert rec.live is None
        [closed] = edits_of(bot, LIVE_MSG)
        assert closed.text == render_final(rec, FinalState.BOOKED, "en")
        assert closed.reply_markup is None

    @pytest.mark.parametrize("outcome", [None, RuntimeError("boom")])
    async def test_failure_keeps_the_watch_and_forgets_nothing(
        self, db, user, context, bot, city, stats, outcome, caplog
    ):
        watch_id = make_watch(db, live=False)
        open_confirming_session(db, watch_id)
        city["results"] = [outcome]

        await tap(booking.confirm, context, "b1:ok")
        await context.drain()

        assert get_watch(db, watch_id).status == "active"
        with Session(db) as session:
            assert UserRepository(session).get_booking_contact(USER) is None
        assert get_booking(db) is None
        assert stats["completed"] == 0
        final = edits_of(bot, LIVE_MSG)[-1]
        assert final.text.endswith("\n\n" + t("booking.will_update", "en"))
        assert buttons(final.reply_markup) == [(t("keyboard.watches", "en"), "w1:list")]
        if outcome is not None:
            assert [
                r.getMessage() for r in caplog.records if r.name == booking.__name__
            ][-1] == "Booking error: boom"

    async def test_failure_for_a_paused_watch_promises_nothing(
        self, db, user, context, bot, city
    ):
        watch_id = make_watch(db, live=False)
        with Session(db) as session:
            WatchRepository(session).set_status(watch_id, "paused", pause_reason="user")
        open_confirming_session(db, watch_id)
        city["results"] = [None]

        await tap(booking.confirm, context, "b1:ok")
        await context.drain()

        assert edits_of(bot, LIVE_MSG)[-1].text == t("booking.failed", "en")

    async def test_new_booking_started_meanwhile_keeps_its_session(
        self, db, user, context, bot, city, fake_availability
    ):
        watch_id = make_watch(db, live=False)
        open_confirming_session(db, watch_id)
        release = asyncio.Event()
        city["results"] = [release]
        await tap(booking.confirm, context, "b1:ok")
        await asyncio.sleep(0)

        other = make_watch(db, FUEHRERSCHEIN, FUEHRERSCHEIN_OFFICE, live=False)
        fake_availability.day_results = [(SlotTime(ts(8), FUEHRERSCHEIN_OFFICE),)]
        await tap(booking.book_day, context, book_data(other), message_id=OLD_MSG)
        release.set()
        await context.drain()

        assert get_booking(db)[:3] == (other, FUEHRERSCHEIN_OFFICE, OLD_MSG)


class TestStaleButtons:
    @pytest.mark.parametrize(
        "data",
        [
            "b1:t:102526:1793264400",
            "b1:me",
            "b1:ok",
            "b1:x",
            "time_1793264400",
            "confirm_booking",
            "cancel_booking",
        ],
    )
    async def test_orphan_button_says_session_cleared(
        self, db, user, context, bot, data
    ):
        update = make_callback_update(data, USER, OLD_MSG, bot=bot)

        await booking.booking_orphan_callback(update, context)

        assert len(bot.calls_of("answer_callback_query")) == 1
        [edit] = bot.edits
        assert (edit.message_id, edit.text, edit.reply_markup) == (
            OLD_MSG,
            t("booking.session_cleared", "en"),
            None,
        )

    async def test_orphan_button_of_an_expired_session_message_deletes_it(
        self, db, user, context, bot
    ):
        open_confirming_session(db, None, message_id=OLD_MSG, expires_in=-1)

        await booking.booking_orphan_callback(
            make_callback_update("b1:ok", USER, OLD_MSG, bot=bot), context
        )

        assert get_booking(db) is None
        assert [e.text for e in bot.edits] == [t("booking.session_cleared", "en")]

    @pytest.mark.parametrize("data", ["b1:t:102526:1793264400", "b1:me", "b1:chg"])
    async def test_repeated_button_of_the_running_booking_is_ignored(
        self, db, user, context, bot, data
    ):
        open_confirming_session(db, None, message_id=OLD_MSG)

        await booking.booking_orphan_callback(
            make_callback_update(data, USER, OLD_MSG, bot=bot), context
        )

        assert get_booking(db) is not None
        assert len(bot.calls_of("answer_callback_query")) == 1
        assert bot.edits == []

    async def test_orphan_button_keeps_a_booking_running_on_another_message(
        self, db, user, context, bot
    ):
        open_confirming_session(db, None, message_id=LIVE_MSG)

        await booking.booking_orphan_callback(
            make_callback_update("b1:t:102526:1793264400", USER, OLD_MSG, bot=bot),
            context,
        )

        assert get_booking(db) is not None
        assert [e.message_id for e in bot.edits] == [OLD_MSG]


class TestRestart:
    async def test_end_all_sessions_edits_their_messages_and_deletes_them(
        self, db, user, bot
    ):
        with Session(db) as session:
            UserRepository(session).create_user(OTHER_USER, language="ru")
            repo = BookingSessionRepository(session)
            for user_id, message_id in ((USER, 11), (OTHER_USER, None)):
                repo.create_session(
                    user_id=user_id,
                    state="ASKING_NAME",
                    service_id=WOHNSITZ,
                    office_id=0,
                    date=DAY.isoformat(),
                    captcha_token="",
                    expires_at=NOW + timedelta(minutes=5),
                    message_id=message_id,
                )

        assert await booking.end_all_booking_sessions(bot) == 2

        assert [
            (e.chat_id, e.message_id, e.text, e.reply_markup) for e in bot.edits
        ] == [(USER, 11, t("booking.session_cleared", "en"), None)]
        assert get_booking(db, USER) is None
        assert get_booking(db, OTHER_USER) is None
