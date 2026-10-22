# ABOUTME: Tests for the My watches screen (S18) and its buttons: pause, resume, stop with confirmation.
# ABOUTME: Real in-memory DB and catalog fixture; Telegram is the recording FakeBot from tests/fakes.py.

import html
from datetime import date, timedelta

import pytest
from sqlmodel import Session
from telegram import InlineKeyboardMarkup

from src.commands.watches import (
    build_watches_screen,
    watches_callback,
    watches_command,
)
from src.handlers import text_input
from src.i18n import t
from src.repositories import PendingRetireRepository, UserRepository, WatchRepository
from src.watches.alert_ops import process_pending_retires
from src.watches.alert_view import render_alert
from src.watches.labels import ago_label, watch_state, watch_summary
from src.watches.slots import Slot, SlotTime, WatchSnapshot
from src.watches.when import PRESETS, WhenSpec
from tests.fakes import FakeBot, FakeContext, make_callback_update, make_text_update

USER = 4242
OTHER = 777
LIST_MSG = 50
OLD_ALERT_MSG = 69
ALERT_MSG = 70
DAY = date(2026, 10, 29)
TS = 1793260800


def add_user(db, language="en", user_id=USER):
    with Session(db) as session:
        UserRepository(session).create_user(user_id, language=language)


def new_watch(db, service_id, office_id=None, when=PRESETS["asap"], user_id=USER):
    with Session(db) as session:
        rec, _ = WatchRepository(session).create_or_update(
            user_id, service_id, office_id, when
        )
        return rec


def get_watch(db, watch_id):
    with Session(db) as session:
        return WatchRepository(session).get(watch_id)


def snapshot(clock, minutes_ago=5):
    return WatchSnapshot(
        checked_at=clock.now - timedelta(minutes=minutes_ago),
        ok=True,
        slots=frozenset({Slot(DAY, 102526), Slot(date(2026, 11, 3), 102522)}),
        earliest_times=(SlotTime(TS, 102526),),
    )


def checked(db, rec, snap):
    with Session(db) as session:
        WatchRepository(session).record_check(rec.id, snap)
    return get_watch(db, rec.id)


def with_live_alert(db, rec, message_id=ALERT_MSG):
    with Session(db) as session:
        WatchRepository(session).set_live_alert(
            rec.id, USER, message_id, "slots", rec.alerted, rec.alerted, "hash"
        )
    return get_watch(db, rec.id)


def set_status(db, rec, status, **kwargs):
    with Session(db) as session:
        return WatchRepository(session).set_status(rec.id, status, **kwargs)


def nav_pointer(db, user_id=USER):
    with Session(db) as session:
        return UserRepository(session).get_nav_message_id(user_id)


def set_nav(db, message_id, user_id=USER):
    with Session(db) as session:
        UserRepository(session).set_nav_message_id(user_id, message_id)


def buttons(markup) -> list[list[tuple[str, str]]]:
    return [
        [(b.text, b.callback_data or b.url) for b in row]
        for row in markup.inline_keyboard
    ]


def line(rec, n, lang, checked_text=""):
    return t(
        "watches.line",
        lang,
        n=n,
        summary=html.escape(watch_summary(rec, lang)),
        state=watch_state(rec, lang),
        checked=checked_text,
    )


@pytest.fixture(autouse=True)
def pending_input(monkeypatch):
    """Records clear_pending_input calls (owned by the find stream)"""
    calls = []
    monkeypatch.setattr(
        text_input, "clear_pending_input", lambda context: calls.append(context)
    )
    return calls


@pytest.fixture
def bot():
    return FakeBot()


@pytest.fixture
def ctx(bot):
    return FakeContext(bot)


class TestBuildScreen:
    def test_empty(self, db, catalog, clock):
        add_user(db)
        text, markup = build_watches_screen(USER, "en", clock.now)
        assert text == t("watches.empty", "en")
        assert buttons(markup) == [[(t("watches.btn_find", "en"), "f1:home")]]

    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_lines_states_and_buttons(self, db, catalog, clock, lang):
        add_user(db, lang)
        slots = checked(db, new_watch(db, 1063475), snapshot(clock, minutes_ago=5))
        none_yet = checked(
            db,
            new_watch(db, 1071896),
            WatchSnapshot(checked_at=clock.now - timedelta(hours=2), ok=True),
        )
        paused = set_status(
            db, new_watch(db, 1063441, 102522), "paused", pause_reason="user"
        )
        unchecked = new_watch(
            db, 1063453, None, WhenSpec("before", date_to=date(2026, 12, 1))
        )
        booked = set_status(db, new_watch(db, 1064305), "ended", end_reason="booked")

        text, markup = build_watches_screen(USER, lang, clock.now)

        def ago(minutes):
            return t(
                "watches.checked", lang, ago=ago_label(timedelta(minutes=minutes), lang)
            )

        assert text == "\n\n".join(
            [
                t("watches.header", lang, count=4, limit=5),
                line(slots, 1, lang, ago(5)),
                line(none_yet, 2, lang, ago(120)),
                line(paused, 3, lang),
                line(unchecked, 4, lang),
                line(booked, 5, lang),
            ]
        )
        assert (
            t(
                "watch.state_slots",
                lang,
                count=2,
                day=t("watch.day", lang, weekday=t("watch.wd_3", lang), date="29.10"),
            )
            in text
        )
        stop, pause, resume = (
            t("watches.btn_stop", lang),
            t("watches.btn_pause", lang),
            t("watches.btn_resume", lang),
        )

        def time_btn(n):
            return t("watches.btn_time", lang, n=n)

        assert buttons(markup) == [
            [
                (time_btn(1), f"f1:edit:{slots.id}"),
                (pause, f"w1:pause:{slots.id}"),
                (stop, f"w1:stop:{slots.id}"),
            ],
            [
                (time_btn(2), f"f1:edit:{none_yet.id}"),
                (pause, f"w1:pause:{none_yet.id}"),
                (stop, f"w1:stop:{none_yet.id}"),
            ],
            [
                (time_btn(3), f"f1:edit:{paused.id}"),
                (resume, f"w1:resume:{paused.id}"),
                (stop, f"w1:stop:{paused.id}"),
            ],
            [
                (time_btn(4), f"f1:edit:{unchecked.id}"),
                (pause, f"w1:pause:{unchecked.id}"),
                (stop, f"w1:stop:{unchecked.id}"),
            ],
            [(t("watches.btn_again", lang, n=5), f"f1:edit:{booked.id}")],
            [(t("watches.btn_new", lang), "f1:home")],
        ]

    def test_no_internal_details(self, db, catalog, clock):
        add_user(db)
        checked(db, new_watch(db, 1063475), snapshot(clock))
        text, _ = build_watches_screen(USER, "en", clock.now)
        assert str(USER) not in text
        assert "interval" not in text.lower()
        assert "users" not in text.lower()

    def test_service_names_are_escaped(self, db, catalog, clock, monkeypatch):
        add_user(db)
        catalog["services"].append({"id": 999, "name": "Pass <b>&</b> Co"})
        new_watch(db, 999)
        text, _ = build_watches_screen(USER, "en", clock.now)
        assert "Pass &lt;b&gt;&amp;&lt;/b&gt; Co" in text

    def test_ended_only_recent_reasons_and_max_three(self, db, catalog, clock):
        add_user(db)
        old = new_watch(db, 1063475)
        set_status(db, old, "ended", end_reason="deadline")
        clock.now += timedelta(days=8)
        stopped = new_watch(db, 1063441)
        set_status(db, stopped, "ended", end_reason="stopped")
        recent = []
        for service_id, reason in (
            (1063453, "booked"),
            (1071896, "deadline"),
            (1064305, "gone"),
            (10339028, "booked"),
        ):
            rec = new_watch(db, service_id)
            recent.append(set_status(db, rec, "ended", end_reason=reason))
            clock.now += timedelta(minutes=1)

        text, markup = build_watches_screen(USER, "en", clock.now)

        assert text.startswith(t("watches.header", "en", count=0, limit=5))
        booked, gone, deadline = reversed(recent[1:])
        assert buttons(markup) == [
            [(t("watches.btn_again", "en", n=1), f"f1:edit:{booked.id}")],
            [(t("watches.btn_any_office", "en", n=2), f"f1:any:{gone.id}")],
            [(t("watches.btn_again", "en", n=3), f"f1:edit:{deadline.id}")],
            [(t("watches.btn_new", "en"), "f1:home")],
        ]

    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_gone_office_offers_any_office(self, db, catalog, clock, lang):
        add_user(db, lang)
        gone = set_status(
            db, new_watch(db, 1063475, 999001), "ended", end_reason="gone"
        )

        text, markup = build_watches_screen(USER, lang, clock.now)

        assert line(gone, 1, lang) in text
        assert buttons(markup) == [
            [(t("watches.btn_any_office", lang, n=1), f"f1:any:{gone.id}")],
            [(t("watches.btn_new", lang), "f1:home")],
        ]

    def test_gone_service_has_no_watch_button(self, db, catalog, clock):
        add_user(db)
        catalog["services"].append({"id": 999, "name": "Nicht mehr online"})
        gone = set_status(db, new_watch(db, 999), "ended", end_reason="gone")

        text, markup = build_watches_screen(USER, "en", clock.now)

        assert line(gone, 1, "en") in text
        assert buttons(markup) == [[(t("watches.btn_new", "en"), "f1:home")]]

    def test_limit_hides_new(self, db, catalog, clock):
        add_user(db)
        for service_id in (1063475, 1063441, 1063453, 1071896, 1064305):
            new_watch(db, service_id)
        text, markup = build_watches_screen(USER, "en", clock.now)
        assert text.startswith(t("watches.header", "en", count=5, limit=5))
        assert all(data != "f1:home" for row in buttons(markup) for _, data in row)


@pytest.mark.asyncio
class TestCommand:
    async def test_sends_list_and_strips_previous_nav(
        self, db, catalog, clock, bot, ctx, pending_input
    ):
        add_user(db, "ru")
        new_watch(db, 1063475)
        set_nav(db, 33)

        await watches_command(make_text_update("/watches", bot=bot), ctx)

        [sent] = bot.sent
        expected_text, expected_markup = build_watches_screen(USER, "ru", clock.now)
        assert sent.text == expected_text
        assert sent.reply_markup == expected_markup
        assert sent.parse_mode == "HTML"
        [strip] = bot.calls_of("edit_message_reply_markup")
        assert strip.message_id == 33
        assert nav_pointer(db) == sent.message_id
        assert pending_input == [ctx]

    async def test_unregistered_user(self, db, catalog, clock, bot, ctx):
        await watches_command(make_text_update("/watches", bot=bot), ctx)
        assert [s.text for s in bot.sent] == [t("start.not_registered", "en")]


@pytest.mark.asyncio
class TestPauseResume:
    async def test_pause_closes_live_alert_and_rerenders(
        self, db, catalog, clock, bot, ctx, pending_input
    ):
        add_user(db)
        rec = with_live_alert(db, checked(db, new_watch(db, 1063475), snapshot(clock)))
        update = make_callback_update(
            f"w1:pause:{rec.id}", message_id=LIST_MSG, bot=bot
        )

        await watches_callback(update, ctx)

        paused = get_watch(db, rec.id)
        assert (paused.status, paused.pause_reason, paused.live) == (
            "paused",
            "user",
            None,
        )
        alert_edit, list_edit = bot.edits
        assert alert_edit.message_id == ALERT_MSG
        assert alert_edit.text == t(
            "alert.final_paused", "en", summary=html.escape(watch_summary(rec, "en"))
        )
        assert alert_edit.reply_markup is None
        assert list_edit.message_id == LIST_MSG
        assert (list_edit.text, list_edit.reply_markup) == build_watches_screen(
            USER, "en", clock.now
        )
        assert (t("watches.btn_resume", "en"), f"w1:resume:{rec.id}") in buttons(
            list_edit.reply_markup
        )[0]
        assert len(bot.calls_of("answer_callback_query")) == 1
        assert pending_input == [ctx]
        assert nav_pointer(db) == LIST_MSG

    async def test_resume(self, db, catalog, clock, bot, ctx):
        add_user(db)
        rec = set_status(db, new_watch(db, 1063475), "paused", pause_reason="user")

        await watches_callback(
            make_callback_update(f"w1:resume:{rec.id}", message_id=LIST_MSG, bot=bot),
            ctx,
        )

        assert get_watch(db, rec.id).status == "active"
        [edit] = bot.edits
        assert (t("watches.btn_pause", "en"), f"w1:pause:{rec.id}") in buttons(
            edit.reply_markup
        )[0]

    async def test_pause_of_other_users_watch_changes_nothing(
        self, db, catalog, clock, bot, ctx
    ):
        add_user(db)
        add_user(db, user_id=OTHER)
        rec = new_watch(db, 1063475, user_id=OTHER)

        await watches_callback(
            make_callback_update(f"w1:pause:{rec.id}", message_id=LIST_MSG, bot=bot),
            ctx,
        )

        assert get_watch(db, rec.id).status == "active"
        [answer] = bot.calls_of("answer_callback_query")
        assert answer.text == t("watches.not_open", "en")


@pytest.mark.asyncio
class TestStopFromList:
    async def test_ask_then_yes(self, db, catalog, clock, bot, ctx):
        add_user(db)
        rec = with_live_alert(db, checked(db, new_watch(db, 1063475), snapshot(clock)))
        summary = html.escape(watch_summary(rec, "en"))

        await watches_callback(
            make_callback_update(f"w1:stop:{rec.id}", message_id=LIST_MSG, bot=bot),
            ctx,
        )

        [confirm] = bot.edits
        assert confirm.message_id == LIST_MSG
        assert confirm.text == t("watches.stop_confirm", "en", summary=summary)
        assert buttons(confirm.reply_markup) == [
            [
                (t("watches.btn_stop_yes", "en"), f"w1:stopy:{rec.id}"),
                (t("watches.btn_stop_no", "en"), f"w1:stopn:{rec.id}"),
            ]
        ]
        assert nav_pointer(db) == LIST_MSG

        await watches_callback(
            make_callback_update(f"w1:stopy:{rec.id}", message_id=LIST_MSG, bot=bot),
            ctx,
        )

        stopped = get_watch(db, rec.id)
        assert (stopped.status, stopped.end_reason, stopped.live) == (
            "ended",
            "stopped",
            None,
        )
        _, final, listing = bot.edits
        assert final.message_id == ALERT_MSG
        assert final.text == t("alert.final_stopped", "en", summary=summary)
        assert listing.message_id == LIST_MSG
        assert listing.text == t("watches.empty", "en")

    async def test_no_returns_to_list(self, db, catalog, clock, bot, ctx):
        add_user(db)
        rec = new_watch(db, 1063475)

        await watches_callback(
            make_callback_update(f"w1:stopn:{rec.id}", message_id=LIST_MSG, bot=bot),
            ctx,
        )

        assert get_watch(db, rec.id).status == "active"
        [edit] = bot.edits
        assert (edit.text, edit.reply_markup) == build_watches_screen(
            USER, "en", clock.now
        )

    async def test_yes_on_ended_watch_is_a_toast(self, db, catalog, clock, bot, ctx):
        add_user(db)
        rec = set_status(db, new_watch(db, 1063475), "ended", end_reason="stopped")

        await watches_callback(
            make_callback_update(f"w1:stopy:{rec.id}", message_id=ALERT_MSG, bot=bot),
            ctx,
        )

        [answer] = bot.calls_of("answer_callback_query")
        assert answer.text == t("watches.not_open", "en")
        assert bot.edits == []
        [strip] = bot.calls_of("edit_message_reply_markup")
        assert strip.message_id == ALERT_MSG

    async def test_stop_on_a_queued_old_alert_is_not_retired_later(
        self, db, catalog, clock, bot, ctx
    ):
        add_user(db)
        rec = with_live_alert(db, checked(db, new_watch(db, 1063475), snapshot(clock)))
        with Session(db) as session:
            PendingRetireRepository(session).add(
                USER, USER, OLD_ALERT_MSG, "OUTDATED", clock.now
            )

        for action in ("stop", "stopy"):
            await watches_callback(
                make_callback_update(
                    f"w1:{action}:{rec.id}", message_id=OLD_ALERT_MSG, bot=bot
                ),
                ctx,
            )
        listing = bot.edits[-1]
        assert listing.message_id == OLD_ALERT_MSG
        assert listing.text == t("watches.empty", "en")
        assert nav_pointer(db) == OLD_ALERT_MSG

        clock.now += timedelta(minutes=11)
        edits_before = len(bot.edits)
        await process_pending_retires(bot, clock.now)

        assert len(bot.edits) == edits_before


@pytest.mark.asyncio
class TestStopFromAlert:
    async def test_confirm_in_place_without_becoming_nav(
        self, db, catalog, clock, bot, ctx
    ):
        add_user(db)
        set_nav(db, LIST_MSG)
        rec = with_live_alert(db, checked(db, new_watch(db, 1063475), snapshot(clock)))

        await watches_callback(
            make_callback_update(f"w1:stop:{rec.id}", message_id=ALERT_MSG, bot=bot),
            ctx,
        )

        [confirm] = bot.edits
        assert confirm.message_id == ALERT_MSG
        assert confirm.text == t(
            "watches.stop_confirm", "en", summary=html.escape(watch_summary(rec, "en"))
        )
        assert bot.calls_of("edit_message_reply_markup") == []
        assert nav_pointer(db) == LIST_MSG
        assert get_watch(db, rec.id).live.message_id == ALERT_MSG

    async def test_no_rerenders_alert_from_snapshot(self, db, catalog, clock, bot, ctx):
        add_user(db, "ru")
        rec = with_live_alert(db, checked(db, new_watch(db, 1063475), snapshot(clock)))

        await watches_callback(
            make_callback_update(f"w1:stopn:{rec.id}", message_id=ALERT_MSG, bot=bot),
            ctx,
        )

        [edit] = bot.edits
        expected = render_alert(rec, rec.snapshot, "ru", initial=False)
        assert edit.message_id == ALERT_MSG
        assert edit.text == expected.text
        assert edit.reply_markup == expected.markup
        assert isinstance(edit.reply_markup, InlineKeyboardMarkup)
        assert get_watch(db, rec.id).status == "active"
        assert nav_pointer(db) is None

    async def test_yes_finalizes_alert_only(self, db, catalog, clock, bot, ctx):
        add_user(db)
        set_nav(db, LIST_MSG)
        rec = with_live_alert(db, checked(db, new_watch(db, 1063475), snapshot(clock)))

        await watches_callback(
            make_callback_update(f"w1:stopy:{rec.id}", message_id=ALERT_MSG, bot=bot),
            ctx,
        )

        [final] = bot.edits
        assert final.message_id == ALERT_MSG
        assert final.text == t(
            "alert.final_stopped", "en", summary=html.escape(watch_summary(rec, "en"))
        )
        assert final.reply_markup is None
        assert get_watch(db, rec.id).status == "ended"
        assert nav_pointer(db) == LIST_MSG


@pytest.mark.asyncio
class TestListButton:
    async def test_list_edits_pressed_message(self, db, catalog, clock, bot, ctx):
        add_user(db)
        new_watch(db, 1063475)

        await watches_callback(
            make_callback_update("w1:list", message_id=LIST_MSG, bot=bot), ctx
        )

        [edit] = bot.edits
        assert edit.message_id == LIST_MSG
        assert (edit.text, edit.reply_markup) == build_watches_screen(
            USER, "en", clock.now
        )

    async def test_malformed_data_shows_list(self, db, catalog, clock, bot, ctx):
        add_user(db)
        await watches_callback(
            make_callback_update("w1:pause:x", message_id=LIST_MSG, bot=bot), ctx
        )
        [edit] = bot.edits
        assert edit.text == t("watches.empty", "en")
