# ABOUTME: Tests for /stop and deleting all of a user's data (S21, S22): confirmation, finalized
# ABOUTME: messages, cascade over every table, cleared handler state. Real in-memory DB, FakeBot.

import html
from datetime import date, timedelta

import pytest
from sqlmodel import Session, select
from telegram import ReplyKeyboardRemove
from telegram.error import NetworkError

from src.commands import settings as settings_module
from src.commands import stop as stop_module
from src.commands.settings import settings_callback
from src.commands.stop import delete_user_data, stop_command
from src.db_models import (
    BookingSession,
    PendingRetire,
    ServiceSubscription,
    User,
    Watch,
)
from src.handlers import text_input
from src.i18n import t
from src.repositories import (
    BookingSessionRepository,
    PendingRetireRepository,
    UserRepository,
    WatchRepository,
)
from src.services.alert_lifecycle import apply_alert
from src.ui.screens import retire_nav_message
from src.watches.alert_decision import AlertAction
from src.watches.labels import watch_summary
from src.watches.slots import Slot, SlotTime, WatchSnapshot
from src.watches.when import PRESETS
from tests.fakes import FakeBot, FakeContext, make_callback_update, make_text_update

pytestmark = pytest.mark.asyncio

USER = 4242
OTHER = 777
NAV_MSG = 60
CONFIRM_MSG = 61
ALERT_MSG = 70
ENDED_ALERT_MSG = 72
BOOKING_MSG = 80
QUEUED_MSG = 90


def add_user(db, language="en", user_id=USER):
    with Session(db) as session:
        UserRepository(session).create_user(user_id, language=language)


def rows(db, model, user_id=USER):
    with Session(db) as session:
        return session.exec(select(model).where(model.user_id == user_id)).all()


def nav_pointer(db):
    with Session(db) as session:
        return UserRepository(session).get_nav_message_id(USER)


def buttons(markup) -> list[list[tuple[str, str]]]:
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


def full_account(db, clock, user_id=USER, lang="en"):
    """Open watch with a live alert, an ended one with its S17 message, a booking session,
    a queued retire, a legacy subscription and a nav pointer"""
    add_user(db, lang, user_id)
    with Session(db) as session:
        watches = WatchRepository(session)
        live, _ = watches.create_or_update(user_id, 1063475, None, PRESETS["asap"])
        watches.set_live_alert(
            live.id, user_id, ALERT_MSG, "slots", frozenset(), frozenset(), "h"
        )
        paused, _ = watches.create_or_update(user_id, 1063441, None, PRESETS["2w"])
        watches.set_status(paused.id, "paused", pause_reason="user")
        ended, _ = watches.create_or_update(user_id, 1063453, None, PRESETS["1m"])
        watches.set_status(ended.id, "ended", end_reason="deadline")
        watches.set_live_alert(
            ended.id, user_id, ENDED_ALERT_MSG, "ended", frozenset(), frozenset(), "h"
        )
        BookingSessionRepository(session).create_session(
            user_id=user_id,
            state="select_time",
            service_id=1063475,
            office_id=0,
            date="2026-10-29",
            captcha_token="",
            expires_at=clock.now + timedelta(minutes=10),
            watch_id=live.id,
            message_id=BOOKING_MSG,
        )
        PendingRetireRepository(session).add(
            user_id, user_id, QUEUED_MSG, "queued final", clock.now + timedelta(hours=1)
        )
        session.add(
            ServiceSubscription(user_id=user_id, service_id=1063475, office_id=102526)
        )
        session.commit()
        UserRepository(session).set_nav_message_id(user_id, NAV_MSG)
        return (
            watches.get(live.id),
            watches.get(paused.id),
            watches.get(ended.id),
        )


@pytest.fixture(autouse=True)
def pending_input(monkeypatch):
    calls = []
    monkeypatch.setattr(
        text_input, "clear_pending_input", lambda context: calls.append(context)
    )
    return calls


@pytest.fixture(autouse=True)
def tracked(events):
    events.patch(settings_module)
    return events


@pytest.fixture
def bot():
    return FakeBot()


@pytest.fixture
def ctx(bot):
    return FakeContext(bot, user_data={"lang": "en", "await_date": {"kind": "before"}})


class TestStopCommand:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_asks_for_confirmation(self, db, bot, ctx, pending_input, lang):
        add_user(db, lang)
        ctx.user_data.pop("lang")

        await stop_command(make_text_update("/stop", bot=bot), ctx)

        [sent] = bot.sent
        assert sent.text == t("stop.confirm", lang)
        assert buttons(sent.reply_markup) == [
            [(t("stop.btn_yes", lang), "s1:dely"), (t("stop.btn_no", lang), "s1:deln")]
        ]
        assert nav_pointer(db) == sent.message_id
        assert pending_input == [ctx]
        with Session(db) as session:
            assert UserRepository(session).get_user(USER) is not None

    async def test_unregistered(self, db, bot, ctx):
        await stop_command(make_text_update("/stop", bot=bot), ctx)
        assert [s.text for s in bot.sent] == [t("start.not_registered", "en")]

    async def test_no_after_stop_command_says_kept(self, db, bot, ctx):
        add_user(db, "ru")
        ctx.user_data.pop("lang")
        await stop_command(make_text_update("/stop", bot=bot), ctx)
        [confirm] = bot.sent

        await settings_callback(
            make_callback_update("s1:deln", message_id=confirm.message_id, bot=bot), ctx
        )

        [edit] = bot.edits
        assert edit.message_id == confirm.message_id
        assert edit.text == t("stop.kept", "ru")
        assert edit.reply_markup is None
        assert nav_pointer(db) is None
        assert rows(db, User) != []


class TestDeleteUserData:
    async def test_finalizes_messages_and_deletes_every_row(self, db, catalog, clock):
        live, _, ended = full_account(db, clock)
        full_account(db, clock, user_id=OTHER)
        bot = FakeBot()

        await delete_user_data(bot, USER, "en")

        edits = {e.message_id: e for e in bot.edits if e.chat_id == USER}
        assert edits[ALERT_MSG].text == t(
            "alert.final_stopped", "en", summary=html.escape(watch_summary(live, "en"))
        )
        assert edits[ENDED_ALERT_MSG].text == t(
            "alert.final_stopped", "en", summary=html.escape(watch_summary(ended, "en"))
        )
        assert edits[BOOKING_MSG].text == t("booking.session_cleared", "en")
        assert edits[QUEUED_MSG].text == "queued final"
        assert all(e.reply_markup is None for e in edits.values())
        assert [
            (c.chat_id, c.message_id) for c in bot.calls_of("edit_message_reply_markup")
        ] == [(USER, NAV_MSG)]
        assert all(e.chat_id == USER for e in bot.edits)

        for model in (User, Watch, BookingSession, ServiceSubscription, PendingRetire):
            assert rows(db, model) == []
            assert rows(db, model, OTHER) != []
        with Session(db) as session:
            watches = WatchRepository(session)
            assert watches.get(live.id) is None
            assert {r.user_id for r in watches.list_active()} == {OTHER}

    async def test_check_cycle_during_deletion_sends_nothing(
        self, db, catalog, clock, monkeypatch
    ):
        live, _, _ = full_account(db, clock)
        snap = WatchSnapshot(
            checked_at=clock.now,
            ok=True,
            slots=frozenset({Slot(date(2026, 10, 29), 102526)}),
            earliest_times=(SlotTime(1793260800, 102526),),
        )
        with Session(db) as session:
            watches = WatchRepository(session)
            no_alert, _ = watches.create_or_update(USER, 1071896, None, PRESETS["asap"])
            for watch_id in (live.id, no_alert.id):
                watches.record_check(watch_id, snap)
        bot = FakeBot()
        actions = []

        async def cycle_then_retire(bot_, user_id):
            for watch_id in (live.id, no_alert.id):
                actions.append(
                    await apply_alert(bot_, watch_id, snap, clock.now, lambda _: False)
                )
            await retire_nav_message(bot_, user_id)

        monkeypatch.setattr(stop_module, "retire_nav_message", cycle_then_retire)

        await delete_user_data(bot, USER, "en")

        assert actions == [AlertAction.NOOP, AlertAction.NOOP]
        assert bot.sent == []
        assert rows(db, Watch) == []

    async def test_alert_whose_close_failed_is_finalized_before_the_cascade(
        self, db, catalog, clock, caplog
    ):
        live, _, _ = full_account(db, clock)
        bot = FakeBot()
        bot.fail_next("edit_message_text", NetworkError("down"))

        await delete_user_data(bot, USER, "en")

        final = t(
            "alert.final_stopped", "en", summary=html.escape(watch_summary(live, "en"))
        )
        assert [e.text for e in bot.edits if e.message_id == ALERT_MSG] == [final]
        assert rows(db, PendingRetire) == []
        assert [r.getMessage() for r in caplog.records if r.levelname == "WARNING"] == [
            f"edit chat={USER} message={ALERT_MSG}: failed (down)"
        ]

    async def test_user_without_anything(self, db):
        add_user(db)
        bot = FakeBot()
        await delete_user_data(bot, USER, "en")
        assert bot.calls == []
        assert rows(db, User) == []


class TestDeleteButton:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_yes_deletes_in_background_and_says_goodbye(
        self, db, catalog, clock, bot, ctx, tracked, lang
    ):
        full_account(db, clock, lang=lang)
        ctx.user_data["lang"] = lang
        update = make_callback_update("s1:dely", message_id=CONFIRM_MSG, bot=bot)

        await settings_callback(update, ctx)
        assert len(bot.calls_of("answer_callback_query")) == 1
        await ctx.drain()

        assert rows(db, User) == []
        assert rows(db, Watch) == []
        [deleted] = bot.calls_of("delete_message")
        assert deleted.message_id == CONFIRM_MSG
        done = bot.sent[-1]
        assert done.text == t("stop.done", lang)
        assert isinstance(done.reply_markup, ReplyKeyboardRemove)
        assert ctx.user_data == {}
        [(name, props)] = tracked.calls
        assert name == "user_stopped"
        assert props["user_id"] == USER
        assert props["watches_at_stop"] == 2

    async def test_works_for_user_without_language(self, db, bot, ctx):
        add_user(db, "")
        ctx.user_data.clear()

        await settings_callback(
            make_callback_update("s1:dely", message_id=CONFIRM_MSG, bot=bot), ctx
        )
        await ctx.drain()

        assert rows(db, User) == []
        assert bot.sent[-1].text == t("stop.done", "en")

    async def test_second_tap_after_deletion_sends_nothing_more(self, db, bot, ctx):
        add_user(db)
        update = make_callback_update("s1:dely", message_id=CONFIRM_MSG, bot=bot)

        await settings_callback(update, ctx)
        await settings_callback(
            make_callback_update("s1:dely", message_id=CONFIRM_MSG, bot=bot), ctx
        )
        await ctx.drain()

        assert [s.text for s in bot.sent] == [t("stop.done", "en")]
