# ABOUTME: Tests for the Find flow: popular services, browsing, office and time steps, editing a watch.
# ABOUTME: Real handlers against an in-memory DB, the test catalog and a recording FakeBot.

import asyncio
import html
from datetime import date

import pytest
from sqlmodel import Session

from src import services_manager
from src.commands.find import (
    build_find_screen,
    find_callback,
    find_command,
    show_category_page,
    show_service_step,
    show_when_step,
)
from src.handlers.text_input import AWAIT_KEY
from src.i18n import t
from src.repositories import MAX_OPEN_WATCHES, UserRepository, WatchRepository
from src.services_manager import CATEGORY_KEYWORDS, categorize_services
from src.ui import callbacks as cb
from src.watches.availability import CallResult
from src.watches.labels import POPULAR_SERVICE_IDS, service_label, watch_summary
from src.watches.slots import Slot
from src.watches.when import PRESETS, WhenSpec
from tests.conftest import BUERGERBUERO
from tests.fakes import calendar, make_callback_update, make_text_update

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db", "catalog", "today", "clock"),
]

USER = 4242
MSG = 50
ANMELDUNG = 1063475  # 7 public offices
URGENT = 10339028  # 1 public office
URGENT_OFFICE = 10461
FORSTENRIED = 102526
OTHER_SERVICES = (10339027, 10502137, 1063441, 1063453, 1071896, 1064305)


def register(db, lang="en", user_id=USER):
    with Session(db) as session:
        UserRepository(session).create_user(user_id, language=lang)


def watches(db):
    return WatchRepository(Session(db))


def open_watch(db, service_id, office_id=None, when=PRESETS["asap"], user_id=USER):
    with Session(db) as session:
        rec, _ = WatchRepository(session).create_or_update(
            user_id, service_id, office_id, when
        )
        return rec


def get_watch(db, watch_id):
    with Session(db) as session:
        return WatchRepository(session).get(watch_id)


def nav_pointer(db, user_id=USER):
    with Session(db) as session:
        return UserRepository(session).get_nav_message_id(user_id)


def set_nav_pointer(db, message_id, user_id=USER):
    with Session(db) as session:
        UserRepository(session).set_nav_message_id(user_id, message_id)


def rows(markup):
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


def data_rows(markup):
    return [[b.callback_data for b in row] for row in markup.inline_keyboard]


async def press(context, data, message_id=MSG, user_id=USER):
    update = make_callback_update(data, user_id, message_id, bot=context.bot)
    await find_callback(update, context)
    return update


def last_screen(bot):
    """(text, markup) of the last edit or send"""
    call = [c for c in bot.calls if c.method in ("edit_message_text", "send_message")][
        -1
    ]
    return call.text, call.reply_markup


def slots_result():
    return CallResult(
        True,
        calendar(
            days={"2026-10-29": [URGENT_OFFICE]},
            times={"2026-10-29": [(1793260800, URGENT_OFFICE)]},
        ),
        None,
    )


class TestFindScreen:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_popular_services_in_order_one_per_row(self, lang):
        text, markup = build_find_screen(lang)
        assert text == t("find.title", lang)
        popular = [b for row in markup.inline_keyboard[:-1] for b in row]
        assert [b.callback_data for b in popular] == [
            cb.find_service(sid) for sid in POPULAR_SERVICE_IDS
        ]
        assert all(len(row) == 1 for row in markup.inline_keyboard[:-1])
        for button, sid in zip(popular, POPULAR_SERVICE_IDS):
            assert button.text.endswith(" " + t(f"watch.svc_{sid}", lang))
            assert not button.text.startswith(t(f"watch.svc_{sid}", lang))
        assert rows(markup)[-1] == [(t("find.btn_all", lang), cb.find_all())]

    async def test_services_missing_from_catalog_are_skipped(
        self, monkeypatch, catalog
    ):
        services = [s for s in catalog["services"] if s["id"] != 10502137]
        monkeypatch.setattr(services_manager, "_services_cache", services)
        _, markup = build_find_screen("en")
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert cb.find_service(10502137) not in data
        assert len(data) == len(POPULAR_SERVICE_IDS)

    async def test_find_command_sends_new_nav_screen(self, db, context):
        register(db)
        set_nav_pointer(db, 7)
        context.user_data[AWAIT_KEY] = {"kind": "before"}
        await find_command(make_text_update("/find", USER, bot=context.bot), context)
        sent = context.bot.sent[-1]
        assert sent.text == t("find.title", "en")
        assert nav_pointer(db) == sent.message_id
        strip = context.bot.calls_of("edit_message_reply_markup")
        assert [c.message_id for c in strip] == [7]
        assert AWAIT_KEY not in context.user_data

    async def test_find_command_unregistered(self, db, context):
        await find_command(make_text_update("/find", USER, bot=context.bot), context)
        assert context.bot.sent[-1].text == t("start.not_registered", "en")

    async def test_unregistered_gets_the_telegram_client_language(self, db, context):
        update = make_text_update("/find", USER, bot=context.bot, language_code="ru")
        await find_command(update, context)
        assert context.bot.sent[-1].text == t("start.not_registered", "ru")

    async def test_home_button_edits_pressed_message(self, db, context):
        register(db, "ru")
        await press(context, cb.find_home())
        edit = context.bot.edits[-1]
        assert edit.message_id == MSG
        assert edit.text == t("find.title", "ru")
        assert context.bot.calls_of("answer_callback_query")

    async def test_unknown_find_data_shows_home(self, db, context):
        register(db)
        await press(context, "f1:bogus:1")
        assert context.bot.edits[-1].text == t("find.title", "en")

    async def test_unregistered_button(self, db, context):
        await press(context, cb.find_home())
        assert last_screen(context.bot)[0] == t("start.not_registered", "en")


class TestBrowse:
    async def test_categories(self, db, context):
        register(db)
        await press(context, cb.find_all())
        text, markup = last_screen(context.bot)
        assert text == t("find.categories", "en")
        grouped = categorize_services()
        expected = [
            (f"{t(f'categories.{cid}', 'en')} ({len(grouped[cid])})", f"f1:cat:{cid}:0")
            for cid in CATEGORY_KEYWORDS
            if grouped.get(cid)
        ]
        flat = [b for row in rows(markup)[:-1] for b in row]
        assert flat == expected
        assert all(len(row) <= 2 for row in rows(markup))
        assert rows(markup)[-1] == [(t("find.btn_back", "en"), cb.find_home())]

    @pytest.fixture
    def many_gewerbe(self, monkeypatch, catalog):
        extra = [{"id": 900 + i, "name": f"Gewerbe Nummer {i:02d}"} for i in range(22)]
        monkeypatch.setattr(
            services_manager, "_services_cache", catalog["services"] + extra
        )
        return 23  # plus "Gewerbe-Anmeldung"

    async def test_category_first_page(self, db, context, many_gewerbe):
        register(db)
        await press(context, cb.find_category("gewerbe", 0))
        text, markup = last_screen(context.bot)
        assert text == t(
            "find.category_page",
            "en",
            category=t("categories.gewerbe", "en"),
            first=1,
            last=10,
            total=many_gewerbe,
        )
        services = rows(markup)[:10]
        assert all(len(row) == 1 for row in services)
        assert [row[0][1] for row in services] == [
            cb.find_service(s["id"]) for s in categorize_services()["gewerbe"][:10]
        ]
        assert rows(markup)[10] == [(t("find.btn_next", "en"), "f1:cat:gewerbe:1")]
        assert rows(markup)[11] == [(t("find.btn_back", "en"), cb.find_all())]

    async def test_category_middle_and_last_page(self, db, context, many_gewerbe):
        register(db)
        await press(context, cb.find_category("gewerbe", 1))
        _, markup = last_screen(context.bot)
        assert data_rows(markup)[10] == ["f1:cat:gewerbe:0", "f1:cat:gewerbe:2"]

        await press(context, cb.find_category("gewerbe", 2))
        text, markup = last_screen(context.bot)
        assert "21" in text and "23" in text
        assert len(data_rows(markup)) == 3 + 2
        assert data_rows(markup)[3] == ["f1:cat:gewerbe:1"]

    async def test_page_beyond_the_end_shows_last_page(self, db, context, many_gewerbe):
        register(db)
        await press(context, cb.find_category("gewerbe", 9))
        assert data_rows(last_screen(context.bot)[1])[3] == ["f1:cat:gewerbe:1"]

    async def test_unknown_category_shows_categories(self, db, context):
        register(db)
        await press(context, cb.find_category("nope", 0))
        assert last_screen(context.bot)[0] == t("find.categories", "en")

    async def test_category_label_is_html_escaped(self, db, context):
        register(db)
        await press(context, cb.find_category("ausweis", 0))
        text = last_screen(context.bot)[0]
        assert "ID card &amp; passport" in text

    async def test_show_category_page_from_another_handler(self, db, context):
        register(db)
        update = make_callback_update("catpage:ausweis:0", USER, MSG, bot=context.bot)
        await show_category_page(update, context, "ausweis", 0)
        assert context.bot.edits[-1].message_id == MSG


class TestServiceStep:
    async def test_single_office_goes_to_when_step(self, db, context):
        register(db)
        await press(context, cb.find_service(URGENT))
        text, markup = last_screen(context.bot)
        assert text == t(
            "find.when",
            "en",
            service=html.escape(service_label(URGENT, "en")),
            where="Servicestelle für Zuwanderung und Einbürgerung",
        )
        assert data_rows(markup) == [
            [cb.find_when(URGENT, None, "asap"), cb.find_when(URGENT, None, "2w")],
            [cb.find_when(URGENT, None, "1m"), cb.find_when(URGENT, None, "3m")],
            [cb.find_date(URGENT, None, "b")],
            [cb.find_date(URGENT, None, "r")],
            [cb.find_home()],
        ]

    async def test_many_offices_show_office_step(self, db, context):
        register(db)
        await press(context, cb.find_service(ANMELDUNG))
        text, markup = last_screen(context.bot)
        assert text == t("find.where", "en", service=service_label(ANMELDUNG, "en"))
        layout = rows(markup)
        assert layout[0] == [
            (t("find.btn_any_office", "en"), cb.find_office(ANMELDUNG, None))
        ]
        offices = [b for row in layout[1:-1] for b in row]
        assert all(len(row) == 2 for row in layout[1:-2])
        labels = [text for text, _ in offices]
        assert labels == sorted(labels)
        assert len(offices) == len(BUERGERBUERO)
        assert "Ruppertstraße · 1" in labels and "Ruppertstraße · 2" in labels
        assert (
            "Forstenrieder Allee",
            cb.find_office(ANMELDUNG, FORSTENRIED),
        ) in offices
        assert layout[-1] == [(t("find.btn_back", "en"), cb.find_home())]

    async def test_offices_sharing_a_booking_queue_are_one_button(
        self, db, context, catalog
    ):
        for office in catalog["offices"]:
            if office["id"] in (10489, 10313237):
                office["sharedBookingOfficeIds"] = [10489, 10313237, 10491]
        register(db)
        await press(context, cb.find_service(ANMELDUNG))
        offices = [b for row in rows(last_screen(context.bot)[1])[1:-1] for b in row]
        assert ("Ruppertstraße", cb.find_office(ANMELDUNG, 10489)) in offices
        assert len(offices) == len(BUERGERBUERO) - 1

    async def test_at_most_ten_offices(self, db, context, catalog):
        extra = [{"id": 70000 + i, "name": f"Bürgerbüro Extra {i}"} for i in range(5)]
        catalog["offices"] += extra
        catalog["relations"] += [
            {"serviceId": ANMELDUNG, "officeId": o["id"], "public": True} for o in extra
        ]
        register(db)
        await press(context, cb.find_service(ANMELDUNG))
        offices = [
            b for row in data_rows(last_screen(context.bot)[1])[1:-1] for b in row
        ]
        assert len(offices) == 10

    async def test_limit_for_a_new_service(self, db, context):
        register(db)
        for sid in OTHER_SERVICES[:MAX_OPEN_WATCHES]:
            open_watch(db, sid)
        await press(context, cb.find_service(ANMELDUNG))
        text, markup = last_screen(context.bot)
        assert text == t("find.limit", "en", count=MAX_OPEN_WATCHES)
        assert rows(markup) == [[(t("keyboard.watches", "en"), cb.watches_list())]]

    async def test_limit_above_the_maximum_says_how_many_to_stop(self, db, context):
        from src.db_models import Watch

        register(db)
        services = (*OTHER_SERVICES, 1063423, 1071907)
        with Session(db) as session:
            session.add_all(
                Watch(user_id=USER, service_id=sid, when_kind="asap")
                for sid in services
            )
            session.commit()
        await press(context, cb.find_service(ANMELDUNG))
        text, _ = last_screen(context.bot)
        assert text == t(
            "find.limit_over", "en", open=8, limit=MAX_OPEN_WATCHES, count=4
        )
        assert "Stop 4 of them" in text

    async def test_no_limit_screen_for_a_watched_service(self, db, context):
        register(db)
        for sid in (ANMELDUNG, *OTHER_SERVICES[: MAX_OPEN_WATCHES - 1]):
            open_watch(db, sid)
        await press(context, cb.find_service(ANMELDUNG))
        assert last_screen(context.bot)[0] == t(
            "find.where", "en", service=service_label(ANMELDUNG, "en")
        )

    async def test_when_step_hints_at_existing_watch(self, db, context):
        register(db)
        open_watch(db, URGENT)
        await press(context, cb.find_service(URGENT))
        text = last_screen(context.bot)[0]
        assert text.endswith(t("find.when_existing", "en"))

    async def test_unknown_service(self, db, context):
        register(db)
        await press(context, cb.find_service(123))
        text, markup = last_screen(context.bot)
        assert text == t("find.unavailable", "en")
        assert data_rows(markup) == [[cb.find_home()]]

    async def test_office_chosen_shows_when_step(self, db, context):
        register(db, "ru")
        await press(context, cb.find_office(ANMELDUNG, FORSTENRIED))
        text, markup = last_screen(context.bot)
        assert text == t(
            "find.when",
            "ru",
            service=service_label(ANMELDUNG, "ru"),
            where="Forstenrieder Allee",
        )
        assert data_rows(markup)[0][0] == cb.find_when(ANMELDUNG, FORSTENRIED, "asap")
        assert data_rows(markup)[-1] == [cb.find_service(ANMELDUNG)]

    async def test_non_public_office_falls_back_to_service_step(self, db, context):
        register(db)
        await press(context, cb.find_office(ANMELDUNG, URGENT_OFFICE))
        assert last_screen(context.bot)[0] == t(
            "find.where", "en", service=service_label(ANMELDUNG, "en")
        )

    async def test_steps_callable_from_another_handler(self, db, context):
        register(db)
        update = make_callback_update("srv:1", USER, MSG, bot=context.bot)
        await show_service_step(update, context, URGENT)
        await show_when_step(update, context, ANMELDUNG, FORSTENRIED)
        assert [e.message_id for e in context.bot.edits] == [MSG, MSG]


class TestPresets:
    async def test_preset_creates_watch_and_checks(
        self, db, context, fake_availability
    ):
        register(db)
        fake_availability.calendar_results.append(slots_result())
        await press(context, cb.find_when(URGENT, None, "2w"))
        await context.drain()

        rec = watches(db).find_open(USER, URGENT)
        assert rec.when == WhenSpec("within", 14)
        assert rec.office_id is None
        assert rec.live.message_id == MSG
        edits = context.bot.edits
        assert edits[0].text == t(
            "find.checking", "en", service=html.escape(service_label(URGENT, "en"))
        )
        assert all(e.message_id == MSG for e in edits)
        assert "🎉" in edits[-1].text

    async def test_office_is_stored(self, db, context, fake_availability):
        register(db)
        fake_availability.calendar_results.append(CallResult(True, calendar(), None))
        await press(context, cb.find_when(ANMELDUNG, FORSTENRIED, "asap"))
        await context.drain()
        assert watches(db).find_open(USER, ANMELDUNG).office_id == FORSTENRIED
        assert fake_availability.calendar_calls[0][1] == [FORSTENRIED]

    async def test_same_service_again_updates_office_and_time(
        self, db, context, fake_availability
    ):
        register(db)
        first = open_watch(db, ANMELDUNG, FORSTENRIED, PRESETS["3m"])
        fake_availability.calendar_results.append(CallResult(True, calendar(), None))
        await press(context, cb.find_when(ANMELDUNG, None, "1m"))
        await context.drain()

        rec = watches(db).find_open(USER, ANMELDUNG)
        assert rec.id == first.id
        assert (rec.office_id, rec.when) == (None, PRESETS["1m"])
        assert watches(db).count_open(USER) == 1
        assert context.bot.edits[-1].text.startswith(t("alert.updated_existing", "en"))

    async def test_double_tap_runs_one_check(self, db, context, fake_availability):
        register(db)
        fake_availability.gate = asyncio.Event()
        fake_availability.calendar_results.append(slots_result())
        await press(context, cb.find_when(URGENT, None, "asap"))
        await asyncio.sleep(0)
        await press(context, cb.find_when(URGENT, None, "asap"))
        fake_availability.gate.set()
        await context.drain()
        assert len(fake_availability.calendar_calls) == 1

        await press(context, cb.find_when(URGENT, None, "asap"))
        await context.drain()
        assert len(fake_availability.calendar_calls) == 1

    async def test_tap_on_live_alert_with_another_time_rechecks(
        self, db, context, fake_availability
    ):
        register(db)
        fake_availability.calendar_results += [slots_result(), slots_result()]
        await press(context, cb.find_when(URGENT, None, "asap"))
        await context.drain()
        await press(context, cb.find_when(URGENT, None, "1m"))
        await context.drain()
        assert len(fake_availability.calendar_calls) == 2

    async def test_unavailable_service(self, db, context, fake_availability):
        register(db)
        await press(context, cb.find_when(123, None, "asap"))
        await context.drain()
        assert last_screen(context.bot)[0] == t("find.unavailable", "en")
        assert fake_availability.calendar_calls == []


class TestEditWatch:
    async def test_edit_shows_when_step_for_the_watch(self, db, context):
        register(db)
        rec = open_watch(db, ANMELDUNG, FORSTENRIED)
        await press(context, cb.find_edit(rec.id))
        text, markup = last_screen(context.bot)
        assert text == t(
            "find.when_edit", "en", summary=html.escape(watch_summary(rec, "en"))
        )
        assert "Forstenrieder Allee" in text
        assert data_rows(markup) == [
            [cb.find_edit_when(rec.id, "asap"), cb.find_edit_when(rec.id, "2w")],
            [cb.find_edit_when(rec.id, "1m"), cb.find_edit_when(rec.id, "3m")],
            [cb.find_edit_date(rec.id, "b")],
            [cb.find_edit_date(rec.id, "r")],
            [cb.watches_list()],
        ]

    async def test_edit_of_foreign_watch_shows_home(self, db, context):
        register(db)
        register(db, user_id=1)
        rec = open_watch(db, ANMELDUNG, user_id=1)
        await press(context, cb.find_edit(rec.id))
        assert last_screen(context.bot)[0] == t("find.title", "en")

    async def test_extend_ended_watch_at_limit(self, db, context):
        register(db)
        rec = open_watch(db, ANMELDUNG)
        watches(db).set_status(rec.id, "ended", end_reason="deadline")
        for sid in OTHER_SERVICES[:MAX_OPEN_WATCHES]:
            open_watch(db, sid)
        await press(context, cb.find_edit(rec.id))
        assert last_screen(context.bot)[0] == t(
            "find.limit", "en", count=MAX_OPEN_WATCHES
        )

    async def test_preset_changes_time_and_retires_old_alert(
        self, db, context, fake_availability
    ):
        register(db)
        rec = open_watch(db, URGENT)
        shown = frozenset({Slot(date(2026, 10, 29), URGENT_OFFICE)})
        watches(db).set_live_alert(rec.id, USER, 30, "slots", shown, shown, "h")
        fake_availability.calendar_results.append(slots_result())

        await press(context, cb.find_edit_when(rec.id, "3m"))
        await context.drain()

        updated = get_watch(db, rec.id)
        assert updated.when == PRESETS["3m"]
        assert updated.live.message_id == MSG
        old = [e for e in context.bot.edits if e.message_id == 30]
        assert [e.text for e in old] == [t("alert.outdated", "en")]

    async def test_time_of_a_stopped_watch_says_search_again(self, db, context):
        register(db)
        rec = open_watch(db, ANMELDUNG, FORSTENRIED)
        watches(db).set_status(rec.id, "ended", end_reason="stopped")
        await press(context, cb.find_edit(rec.id))
        assert last_screen(context.bot)[0] == t(
            "find.when_again", "en", summary=html.escape(watch_summary(rec, "en"))
        )

    async def test_any_office_on_gone_watch(self, db, context, fake_availability):
        register(db)
        rec = open_watch(db, ANMELDUNG, FORSTENRIED)
        watches(db).set_status(rec.id, "ended", end_reason="gone")
        await press(context, cb.find_any(rec.id))
        # Nothing changes before a time is chosen, so Back leaves the ended watch as it was
        gone = get_watch(db, rec.id)
        assert (gone.status, gone.office_id) == ("ended", FORSTENRIED)
        text, markup = last_screen(context.bot)
        assert text == t(
            "find.when",
            "en",
            service=html.escape(service_label(ANMELDUNG, "en")),
            where=t("watch.where_any", "en"),
        )
        assert data_rows(markup)[0][0] == cb.find_when(ANMELDUNG, None, "asap")

        fake_availability.calendar_results.append(CallResult(True, calendar(), None))
        await press(context, cb.find_when(ANMELDUNG, None, "asap"))
        await context.drain()
        watching = watches(db).find_open(USER, ANMELDUNG)
        assert watching.office_id is None and watching.status == "active"
        assert get_watch(db, rec.id).end_reason == "gone"

    async def test_any_office_at_limit(self, db, context):
        register(db)
        rec = open_watch(db, ANMELDUNG, FORSTENRIED)
        watches(db).set_status(rec.id, "ended", end_reason="gone")
        for sid in OTHER_SERVICES[:MAX_OPEN_WATCHES]:
            open_watch(db, sid)
        await press(context, cb.find_any(rec.id))
        assert last_screen(context.bot)[0] == t(
            "find.limit", "en", count=MAX_OPEN_WATCHES
        )
        assert get_watch(db, rec.id).office_id == FORSTENRIED

    async def test_double_tap_on_edit_preset(self, db, context, fake_availability):
        register(db)
        rec = open_watch(db, URGENT)
        fake_availability.calendar_results.append(slots_result())
        await press(context, cb.find_edit_when(rec.id, "1m"))
        await context.drain()
        await press(context, cb.find_edit_when(rec.id, "1m"))
        await context.drain()
        assert len(fake_availability.calendar_calls) == 1

    async def test_reused_ended_alert_is_not_retired_later(
        self, db, context, fake_availability
    ):
        register(db)
        ended = open_watch(db, URGENT)
        watches(db).set_status(ended.id, "ended", end_reason="deadline")
        watches(db).set_live_alert(
            ended.id, USER, 77, "ended", frozenset(), frozenset(), "h"
        )
        empty = CallResult(True, calendar(), None)
        fake_availability.calendar_results += [empty, slots_result()]

        await press(context, cb.find_home(), 77)
        await press(context, cb.find_when(ANMELDUNG, None, "asap"), 77)
        await context.drain()
        await press(context, cb.find_edit_when(ended.id, "asap"), 90)
        await context.drain()

        assert t("alert.outdated", "en") not in [
            e.text for e in context.bot.edits if e.message_id == 77
        ]
        assert watches(db).find_open(USER, ANMELDUNG).live.message_id == 77
        assert get_watch(db, ended.id).live.message_id == 90

    async def test_search_again_with_stale_office_uses_any_office(
        self, db, context, fake_availability
    ):
        register(db)
        rec = open_watch(db, ANMELDUNG, 999999)
        watches(db).set_status(rec.id, "ended", end_reason="gone")

        await press(context, cb.find_edit(rec.id))
        switched = get_watch(db, rec.id)
        assert switched.office_id is None
        text, markup = last_screen(context.bot)
        assert text == t(
            "find.when_again", "en", summary=html.escape(watch_summary(switched, "en"))
        )
        assert data_rows(markup)[0][0] == cb.find_edit_when(rec.id, "asap")

        fake_availability.calendar_results.append(CallResult(True, calendar(), None))
        await press(context, cb.find_edit_when(rec.id, "asap"))
        await context.drain()
        assert 999999 not in fake_availability.calendar_calls[0][1]
        assert get_watch(db, rec.id).status == "active"

    @pytest.mark.parametrize("data", ["ewhen", "edate"])
    async def test_stale_time_button_with_stale_office(
        self, db, context, fake_availability, data
    ):
        register(db)
        rec = open_watch(db, ANMELDUNG, 999999)
        watches(db).set_status(rec.id, "ended", end_reason="gone")
        button = (
            cb.find_edit_when(rec.id, "asap")
            if data == "ewhen"
            else cb.find_edit_date(rec.id, "b")
        )

        await press(context, button)
        await context.drain()

        assert fake_availability.calendar_calls == []
        assert AWAIT_KEY not in context.user_data
        switched = get_watch(db, rec.id)
        assert (switched.office_id, switched.status) == (None, "ended")
        assert data_rows(last_screen(context.bot)[1])[0][0] == cb.find_edit_when(
            rec.id, "asap"
        )

    async def test_search_again_with_stale_office_at_limit(self, db, context):
        register(db)
        rec = open_watch(db, ANMELDUNG, 999999)
        watches(db).set_status(rec.id, "ended", end_reason="gone")
        for sid in OTHER_SERVICES[:MAX_OPEN_WATCHES]:
            open_watch(db, sid)
        await press(context, cb.find_edit(rec.id))
        assert last_screen(context.bot)[0] == t(
            "find.limit", "en", count=MAX_OPEN_WATCHES
        )
        assert get_watch(db, rec.id).office_id == 999999

    @pytest.mark.parametrize("data", ["edit", "ewhen", "edate", "any"])
    async def test_watch_of_unavailable_service(
        self, db, context, fake_availability, data
    ):
        register(db)
        rec = open_watch(db, 123, 999999)
        watches(db).set_status(rec.id, "ended", end_reason="gone")
        button = {
            "edit": cb.find_edit(rec.id),
            "ewhen": cb.find_edit_when(rec.id, "asap"),
            "edate": cb.find_edit_date(rec.id, "r"),
            "any": cb.find_any(rec.id),
        }[data]

        await press(context, button)
        await context.drain()

        text, markup = last_screen(context.bot)
        assert text == t("find.unavailable", "en")
        assert data_rows(markup) == [[cb.find_home()]]
        assert fake_availability.calendar_calls == []
        assert AWAIT_KEY not in context.user_data
        assert get_watch(db, rec.id).office_id == 999999


class TestTypedDatePrompt:
    async def test_before_prompt_for_new_watch(self, db, context):
        register(db)
        await press(context, cb.find_date(ANMELDUNG, FORSTENRIED, "b"))
        text, markup = last_screen(context.bot)
        assert text == t("find.ask_before", "en")
        assert rows(markup) == [[(t("find.btn_cancel", "en"), cb.find_cancel())]]
        assert context.user_data[AWAIT_KEY] == {
            "kind": "before",
            "service_id": ANMELDUNG,
            "office_id": FORSTENRIED,
            "watch_id": None,
            "prompt_msg_id": MSG,
        }

    async def test_range_prompt_for_existing_watch(self, db, context):
        register(db, "ru")
        rec = open_watch(db, URGENT)
        await press(context, cb.find_edit_date(rec.id, "r"))
        assert last_screen(context.bot)[0] == t("find.ask_range", "ru")
        assert context.user_data[AWAIT_KEY] == {
            "kind": "range",
            "service_id": URGENT,
            "office_id": None,
            "watch_id": rec.id,
            "prompt_msg_id": MSG,
        }

    async def test_cancel_returns_to_when_step(self, db, context):
        register(db)
        await press(context, cb.find_date(ANMELDUNG, FORSTENRIED, "r"))
        await press(context, cb.find_cancel())
        assert AWAIT_KEY not in context.user_data
        assert data_rows(last_screen(context.bot)[1])[0][0] == cb.find_when(
            ANMELDUNG, FORSTENRIED, "asap"
        )

    async def test_cancel_for_existing_watch(self, db, context):
        register(db)
        rec = open_watch(db, URGENT)
        await press(context, cb.find_edit_date(rec.id, "b"))
        await press(context, cb.find_cancel())
        assert data_rows(last_screen(context.bot)[1])[0][0] == cb.find_edit_when(
            rec.id, "asap"
        )

    async def test_cancel_without_pending_prompt_shows_home(self, db, context):
        register(db)
        await press(context, cb.find_cancel())
        assert last_screen(context.bot)[0] == t("find.title", "en")

    async def test_any_find_button_clears_pending_prompt(self, db, context):
        register(db)
        await press(context, cb.find_date(ANMELDUNG, None, "b"))
        await press(context, cb.find_all())
        assert AWAIT_KEY not in context.user_data
