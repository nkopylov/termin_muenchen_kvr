# ABOUTME: Tests for the booking conversation steps and the city booking calls behind them.
# ABOUTME: City API and captcha are faked at the HTTP-result level; DB is in-memory, Telegram a FakeBot.

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlmodel import Session
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src import booking_api
from src.commands import booking
from src.i18n import t
from src.munich_api_client import ApiResponse
from src.repositories import BookingSessionRepository, UserRepository, WatchRepository
from src.ui.background import user_lock
from src.ui.callbacks import BOOK_RE, NAV_RE, UNVERSIONED_BOOKING_RE
from src.ui.keyboard import MENU_FILTER
from src.watches.slots import SlotTime
from src.watches.when import PRESETS
from tests.conftest import NOW
from tests.fakes import FakeBot, FakeContext, make_callback_update, make_text_update

TS = 1_793_264_400
OFFICE = 102526
SERVICE = 1063475
SERVICE_NAME = "Wohnsitzanmeldung"
SCOPE = {"id": 1, "provider": {"name": "Bürgerbüro Forstenrieder Allee"}}
RESERVED = {"processId": 77, "authKey": "ak", "timestamp": str(TS), "scope": SCOPE}


def ok(data: dict) -> ApiResponse:
    return ApiResponse(data, 200, ())


def rejected(*codes: str) -> ApiResponse:
    return ApiResponse(None, 400, codes)


async def book() -> dict | None:
    return await booking_api.book_appointment(
        timestamp=TS,
        office_id=OFFICE,
        service_id=SERVICE,
        service_name=SERVICE_NAME,
        family_name="Ivan Petrov",
        email="ivan@example.com",
    )


def posted(fake_api) -> list[tuple[str, dict]]:
    return [(endpoint, data) for method, endpoint, data in fake_api["calls"]]


@pytest.mark.asyncio
class TestBookAppointment:
    async def test_reserve_update_preconfirm_with_a_fresh_token(
        self, fake_api, fake_token
    ):
        fake_api["post"] = [
            ok(RESERVED),
            ok({"processId": 77}),
            ok({"processId": 77, "status": "preconfirmed"}),
        ]

        result = await book()

        assert result == {"processId": 77, "status": "preconfirmed"}
        calls = posted(fake_api)
        assert [endpoint for endpoint, _ in calls] == [
            "reserve-appointment/",
            "update-appointment/",
            "preconfirm-appointment/",
        ]
        reserve = calls[0][1]
        assert reserve["captchaToken"] == "token-1"
        assert (reserve["timestamp"], reserve["officeId"], reserve["serviceId"]) == (
            TS,
            OFFICE,
            [SERVICE],
        )
        for _, data in calls[1:]:
            assert data["serviceName"] == SERVICE_NAME
            assert data["familyName"] == "Ivan Petrov"
            assert data["email"] == "ivan@example.com"
            assert data["officeName"] == "Bürgerbüro Forstenrieder Allee"
        assert fake_token["invalidated"] == 0

    async def test_rejected_token_is_replaced_and_reserve_retried_once(
        self, fake_api, fake_token
    ):
        fake_api["post"] = [
            rejected("captchaInvalid"),
            ok(RESERVED),
            ok({"processId": 77}),
            ok({"processId": 77}),
        ]

        result = await book()

        assert result == {"processId": 77}
        reserves = [d for e, d in posted(fake_api) if e == "reserve-appointment/"]
        assert [d["captchaToken"] for d in reserves] == ["token-1", "token-2"]
        assert fake_token["invalidated"] == 1

    async def test_second_token_rejection_gives_up(self, fake_api, fake_token):
        fake_api["post"] = [rejected("captchaExpired"), rejected("captchaInvalid")]

        assert await book() is None
        assert [e for e, _ in posted(fake_api)] == ["reserve-appointment/"] * 2
        assert fake_token["invalidated"] == 2

    async def test_other_reserve_failure_is_not_retried(self, fake_api, fake_token):
        fake_api["post"] = [rejected("appointmentNotAvailable")]

        assert await book() is None
        assert len(posted(fake_api)) == 1
        assert fake_token["invalidated"] == 0

    async def test_reservation_without_auth_key_fails(self, fake_api, fake_token):
        fake_api["post"] = [ok({"processId": 77})]

        assert await book() is None
        assert len(posted(fake_api)) == 1

    async def test_no_token_means_no_call(self, fake_api, fake_token):
        fake_token["fail"] = True

        assert await book() is None
        assert fake_api["calls"] == []

    @pytest.mark.parametrize("failing_step", [1, 2])
    async def test_failed_later_step_fails_the_booking(
        self, fake_api, fake_token, failing_step
    ):
        replies = [ok(RESERVED), ok({"processId": 77}), ok({"processId": 77})]
        replies[failing_step] = rejected()
        fake_api["post"] = replies

        assert await book() is None
        assert len(posted(fake_api)) == failing_step + 1


# Conversation steps (handlers called directly; a live session makes them stop group 1)

USER = 4242
MSG = 500
NEXT_MSG = 1000
NAME = "Ivan Petrov"
EMAIL = "ivan@example.com"
BERLIN = ZoneInfo("Europe/Berlin")
SLOT_TS = int(datetime(2026, 10, 29, 9, 30, tzinfo=BERLIN).timestamp())
LONG_TIME = "09:30 on Thursday, October 29, 2026"
STEPS = pytest.mark.usefixtures("catalog", "clock", "today")


@pytest.fixture
def bot():
    return FakeBot(first_message_id=NEXT_MSG)


@pytest.fixture
def context(bot):
    return FakeContext(bot, user_data={"lang": "en", "await_date": {"kind": "before"}})


@pytest.fixture(autouse=True)
def quiet_events(events):
    events.patch(booking)
    return events


@pytest.fixture
def user(db):
    with Session(db) as session:
        UserRepository(session).create_user(USER, username="tester", language="en")
    return USER


def save_contact(db, name=NAME, email=EMAIL):
    with Session(db) as session:
        UserRepository(session).set_booking_contact(USER, name, email)


def open_session(
    db, state, *, message_id=MSG, timestamp=None, name=None, email=None, expires_in=15
):
    with Session(db) as session:
        repo = BookingSessionRepository(session)
        repo.create_session(
            user_id=USER,
            state=state,
            service_id=SERVICE,
            office_id=0,
            date="2026-10-29",
            captcha_token="",
            expires_at=NOW + timedelta(minutes=expires_in),
            watch_id=None,
            message_id=message_id,
        )
        repo.update_session(USER, timestamp=timestamp, name=name, email=email)


def session_row(db):
    with Session(db) as session:
        row = BookingSessionRepository(session).get_session(USER)
        if row is None:
            return None
        return {
            "state": row.state,
            "office_id": row.office_id,
            "timestamp": row.timestamp,
            "name": row.name,
            "email": row.email,
            "message_id": row.message_id,
        }


async def run_step(handler, update, context):
    """The state a step hands to the conversation; ("stop", s) when it also stops group 1"""
    try:
        return await handler(update, context)
    except ApplicationHandlerStop as stop:
        return ("stop", stop.state)


async def press(handler, context, data, message_id=MSG):
    return await run_step(
        handler, make_callback_update(data, USER, message_id, bot=context.bot), context
    )


async def type_text(handler, context, text):
    return await run_step(
        handler, make_text_update(text, USER, bot=context.bot, message_id=77), context
    )


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


@pytest.mark.asyncio
@STEPS
class TestTimeSelected:
    async def test_without_saved_contact_asks_for_the_name(
        self, db, user, context, bot
    ):
        open_session(db, "SELECTING_TIME")

        state = await press(booking.time_selected, context, f"b1:t:{OFFICE}:{SLOT_TS}")

        assert state == ("stop", booking.ASKING_NAME)
        [edit] = bot.edits
        assert edit.message_id == MSG
        assert edit.text == t("booking.ask_name", "en", time="Thu 29.10, 09:30")
        assert buttons(edit.reply_markup) == [("❌ Cancel", "b1:x")]
        row = session_row(db)
        assert (row["state"], row["office_id"], row["timestamp"]) == (
            "ASKING_NAME",
            OFFICE,
            SLOT_TS,
        )

    async def test_with_saved_contact_offers_it(self, db, user, context, bot):
        save_contact(db, name="<b>Ivan</b> Petrov", email="ivan@example.com")
        open_session(db, "SELECTING_TIME")

        state = await press(booking.time_selected, context, f"b1:t:{OFFICE}:{SLOT_TS}")

        assert state == ("stop", booking.CONFIRMING)
        [edit] = bot.edits
        assert edit.text == t(
            "booking.use_saved",
            "en",
            time=LONG_TIME,
            office="Forstenrieder Allee",
            name="&lt;b&gt;Ivan&lt;/b&gt; Petrov",
            email="ivan@example.com",
        )
        assert edit.parse_mode == "HTML"
        assert [data for _, data in buttons(edit.reply_markup)] == [
            "b1:me",
            "b1:chg",
            "b1:x",
        ]
        assert session_row(db)["state"] == "CONFIRMING"

    async def test_change_asks_for_the_name(self, db, user, context, bot):
        save_contact(db)
        open_session(db, "CONFIRMING", timestamp=SLOT_TS)

        state = await press(booking.change_contact, context, "b1:chg")

        assert state == ("stop", booking.ASKING_NAME)
        assert bot.edits[-1].text == t(
            "booking.ask_name", "en", time="Thu 29.10, 09:30"
        )
        assert session_row(db)["state"] == "ASKING_NAME"

    async def test_use_saved_contact_books_with_it(
        self, db, user, context, bot, monkeypatch
    ):
        save_contact(db)
        open_session(db, "CONFIRMING", timestamp=SLOT_TS)
        calls = []

        async def book_appointment(**kwargs):
            calls.append(kwargs)
            return {"processId": "P-1"}

        monkeypatch.setattr(booking.booking_api, "book_appointment", book_appointment)

        state = await press(booking.confirm, context, "b1:me")
        assert bot.edits[-1].text == t("booking.processing", "en")
        await context.drain()

        assert state == ("stop", ConversationHandler.END)
        assert [(c["family_name"], c["email"]) for c in calls] == [(NAME, EMAIL)]
        assert session_row(db) is None

    async def test_use_saved_contact_after_it_was_forgotten_asks_for_the_name(
        self, db, user, context, bot
    ):
        open_session(db, "CONFIRMING", timestamp=SLOT_TS)

        state = await press(booking.confirm, context, "b1:me")

        assert state == ("stop", booking.ASKING_NAME)
        assert bot.edits[-1].text == t(
            "booking.ask_name", "en", time="Thu 29.10, 09:30"
        )


@pytest.mark.asyncio
@STEPS
class TestContactSteps:
    async def test_invalid_name_is_asked_again(self, db, user, context, bot):
        open_session(db, "ASKING_NAME", timestamp=SLOT_TS)

        state = await type_text(booking.name_received, context, "Ivan")

        assert state == ("stop", booking.ASKING_NAME)
        assert [s.text for s in bot.sent] == [t("booking.name_not_full", "en")]
        assert bot.calls_of("edit_message_reply_markup") == []
        assert session_row(db)["name"] is None

    async def test_name_moves_buttons_to_the_email_question(
        self, db, user, context, bot
    ):
        open_session(db, "ASKING_NAME", timestamp=SLOT_TS)

        state = await type_text(booking.name_received, context, "  <i>Ivan</i> Petrov ")

        assert state == ("stop", booking.ASKING_EMAIL)
        [sent] = bot.sent
        assert sent.text == t(
            "booking.ask_email", "en", name="&lt;i&gt;Ivan&lt;/i&gt; Petrov"
        )
        assert buttons(sent.reply_markup) == [("❌ Cancel", "b1:x")]
        [strip] = bot.calls_of("edit_message_reply_markup")
        assert (strip.message_id, strip.reply_markup) == (MSG, None)
        row = session_row(db)
        assert (row["name"], row["state"], row["message_id"]) == (
            "<i>Ivan</i> Petrov",
            "ASKING_EMAIL",
            NEXT_MSG,
        )

    async def test_invalid_email_is_asked_again(self, db, user, context, bot):
        open_session(db, "ASKING_EMAIL", timestamp=SLOT_TS, name=NAME)

        state = await type_text(booking.email_received, context, "not-an-email")

        assert state == ("stop", booking.ASKING_EMAIL)
        assert [s.text for s in bot.sent] == [t("booking.email_invalid", "en")]

    async def test_email_shows_the_escaped_confirmation(self, db, user, context, bot):
        open_session(db, "ASKING_EMAIL", timestamp=SLOT_TS, name="Ivan <Petrov>")

        state = await type_text(booking.email_received, context, " Ivan@Example.com ")

        assert state == ("stop", booking.CONFIRMING)
        [sent] = bot.sent
        assert sent.text == t(
            "booking.confirm_summary",
            "en",
            time=LONG_TIME,
            name="Ivan &lt;Petrov&gt;",
            email="ivan@example.com",
        )
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [
            ("✅ Confirm booking", "b1:ok"),
            ("❌ Cancel", "b1:x"),
        ]
        stripped = bot.calls_of("edit_message_reply_markup")
        assert [c.message_id for c in stripped] == [MSG]
        row = session_row(db)
        assert (row["email"], row["state"], row["message_id"]) == (
            "ivan@example.com",
            "CONFIRMING",
            NEXT_MSG,
        )

    @pytest.mark.parametrize(
        "state_name", ["SELECTING_TIME", "ASKING_NAME", "CONFIRMING"]
    )
    async def test_cancel_deletes_the_session_and_keeps_user_data(
        self, db, user, context, bot, state_name
    ):
        open_session(db, state_name, timestamp=SLOT_TS)

        state = await press(booking.cancel, context, "b1:x")

        assert state == ("stop", ConversationHandler.END)
        assert bot.edits[-1].text == t("booking.cancelled", "en")
        assert bot.edits[-1].reply_markup is None
        assert session_row(db) is None
        assert context.user_data == {"lang": "en", "await_date": {"kind": "before"}}

    async def test_button_of_an_older_booking_message_is_only_stripped(
        self, db, user, context, bot
    ):
        open_session(
            db, "ASKING_EMAIL", message_id=NEXT_MSG, timestamp=SLOT_TS, name=NAME
        )

        state = await press(booking.cancel, context, "b1:x", message_id=MSG)

        assert state == ("stop", None)
        stripped = bot.calls_of("edit_message_reply_markup")
        assert [c.message_id for c in stripped] == [MSG]
        assert bot.edits == []
        assert session_row(db) is not None


@pytest.mark.asyncio
@STEPS
class TestStepsWithoutSession:
    @pytest.mark.parametrize("expires_in", [None, -1])
    async def test_text_ends_the_conversation_without_stopping(
        self, db, user, context, bot, expires_in
    ):
        if expires_in is not None:
            open_session(db, "ASKING_NAME", timestamp=SLOT_TS, expires_in=expires_in)

        state = await type_text(booking.name_received, context, NAME)

        assert state == ConversationHandler.END
        assert bot.calls == []

    @pytest.mark.parametrize(
        ("handler", "data"),
        [
            ("time_selected", f"b1:t:{OFFICE}:{SLOT_TS}"),
            ("confirm", "b1:ok"),
            ("change_contact", "b1:chg"),
            ("cancel", "b1:x"),
        ],
    )
    async def test_buttons_end_the_conversation_without_stopping(
        self, db, user, context, bot, handler, data
    ):
        state = await press(getattr(booking, handler), context, data)

        assert state == ConversationHandler.END
        assert bot.calls == []

    async def test_leaving_replaces_the_question_with_cancelled(
        self, db, user, context, bot
    ):
        open_session(db, "ASKING_NAME", timestamp=SLOT_TS)

        state = await type_text(booking.leave_booking, context, "/watches")

        assert state == ConversationHandler.END
        [ended] = bot.edits
        assert (ended.message_id, ended.text, ended.reply_markup) == (
            MSG,
            t("booking.cancelled", "en"),
            None,
        )
        assert session_row(db) is None
        assert context.user_data == {"lang": "en", "await_date": {"kind": "before"}}


# The conversation registered in a real Application, with recording group-1 handlers


@pytest_asyncio.fixture
async def app(db, user, catalog, clock, today, fake_availability):
    application = Application.builder().bot(FakeBot()).updater(None).build()
    seen: list[tuple[str, str]] = []

    def recorder(kind):
        async def record(update, context):
            if update.callback_query is not None:
                seen.append((kind, update.callback_query.data))
            else:
                seen.append((kind, update.message.text))

        return record

    application.add_handler(booking.build_booking_conversation(), group=0)
    for handler in (
        CallbackQueryHandler(recorder("nav"), pattern=NAV_RE),
        CallbackQueryHandler(
            booking.booking_orphan_callback,
            pattern=f"{BOOK_RE}|{UNVERSIONED_BOOKING_RE}",
        ),
        MessageHandler(filters.COMMAND, recorder("command")),
        MessageHandler(MENU_FILTER, recorder("menu")),
        MessageHandler(filters.TEXT & ~filters.COMMAND, recorder("text")),
    ):
        application.add_handler(handler, group=1)
    application.bot_data["seen"] = seen
    application.bot_data["availability"] = fake_availability
    await application.initialize()
    await application.start()
    yield application
    await application.stop()
    await application.shutdown()


def seen(application):
    return application.bot_data["seen"]


async def settle() -> None:
    """Wait for the user's background task started by the last update"""
    await asyncio.sleep(0)
    async with user_lock(USER):
        pass


async def send(application, update) -> None:
    await application.process_update(update)
    await settle()


def callback(application, data, message_id=MSG):
    return make_callback_update(data, USER, message_id, bot=application.bot)


def text(application, value):
    return make_text_update(value, USER, bot=application.bot, message_id=77)


async def start_booking_until_time(application, db) -> None:
    with Session(db) as session:
        watches = WatchRepository(session)
        rec, _ = watches.create_or_update(USER, SERVICE, None, PRESETS["asap"])
        watches.set_live_alert(
            rec.id, USER, MSG, "slots", frozenset(), frozenset(), "h"
        )
    application.bot_data["availability"].day_results = [(SlotTime(SLOT_TS, OFFICE),)]
    await send(application, callback(application, f"b1:{rec.id}:20261029"))
    await send(application, callback(application, f"b1:t:{OFFICE}:{SLOT_TS}"))


async def start_booking_until_name(application, db) -> None:
    await start_booking_until_time(application, db)
    assert session_row(db)["state"] == "ASKING_NAME"


@pytest.mark.asyncio
class TestRegisteredConversation:
    async def test_typed_name_is_not_searched(self, app, db):
        await start_booking_until_name(app, db)

        await send(app, text(app, NAME))

        assert seen(app) == []
        assert session_row(db)["name"] == NAME

    @pytest.mark.parametrize(
        ("update_kind", "value"),
        [
            ("menu", "👀 My watches"),
            ("menu", "👀 Мои поиски"),
            ("command", "/watches"),
            ("nav", "w1:list"),
            ("nav", "s1:home"),
            ("nav", "lang:ru"),
        ],
    )
    async def test_navigation_ends_booking_and_reaches_group_1(
        self, app, db, update_kind, value
    ):
        await start_booking_until_name(app, db)

        update = callback(app, value, 900) if update_kind == "nav" else text(app, value)
        await send(app, update)

        assert seen(app) == [(update_kind, value)]
        assert session_row(db) is None
        ended = [e for e in app.bot.edits if e.message_id == MSG][-1]
        assert (ended.text, ended.reply_markup) == (t("booking.cancelled", "en"), None)

        await send(app, text(app, "passport"))
        assert seen(app)[-1] == ("text", "passport")

    async def test_date_prompt_during_booking_gets_the_typed_date(self, app, db):
        await start_booking_until_name(app, db)

        await send(app, callback(app, f"f1:date:{SERVICE}:0:b", 900))
        await send(app, text(app, "15.11"))

        assert seen(app) == [("nav", f"f1:date:{SERVICE}:0:b"), ("text", "15.11")]
        assert session_row(db) is None

    async def test_text_after_the_session_expired_is_searched(self, app, db, clock):
        await start_booking_until_name(app, db)
        clock.now += timedelta(minutes=16)

        await send(app, text(app, "passport"))
        await send(app, callback(app, "b1:x"))

        assert seen(app) == [("text", "passport")]
        assert app.bot.edits[-1].text == t("booking.session_cleared", "en")

    async def test_cancel_keeps_language_and_pending_input(self, app, db):
        app.user_data[USER]["await_date"] = {"kind": "range"}
        await start_booking_until_name(app, db)

        await send(app, callback(app, "b1:x"))

        assert seen(app) == []
        assert app.user_data[USER]["lang"] == "en"
        assert app.user_data[USER]["await_date"] == {"kind": "range"}
        assert app.bot.edits[-1].text == t("booking.cancelled", "en")

    async def test_button_without_conversation_or_session_is_cleared(self, app, db):
        await send(app, callback(app, f"b1:t:{OFFICE}:{SLOT_TS}"))

        assert seen(app) == []
        assert app.bot.edits[-1].text == t("booking.session_cleared", "en")

    async def test_repeated_time_button_keeps_the_booking(self, app, db):
        await start_booking_until_name(app, db)

        await send(app, callback(app, f"b1:t:{OFFICE}:{SLOT_TS}"))

        assert session_row(db)["state"] == "ASKING_NAME"
        assert app.bot.edits[-1].text == t(
            "booking.ask_name", "en", time="Thu 29.10, 09:30"
        )
        await send(app, text(app, NAME))
        assert seen(app) == []
        assert session_row(db)["name"] == NAME

    async def test_repeated_confirm_keeps_the_running_booking(
        self, app, db, monkeypatch
    ):
        save_contact(db)
        await start_booking_until_time(app, db)
        assert session_row(db)["state"] == "CONFIRMING"
        release = asyncio.Event()

        async def book_appointment(**kwargs):
            await release.wait()
            return {"processId": "P-1"}

        monkeypatch.setattr(booking.booking_api, "book_appointment", book_appointment)

        await app.process_update(callback(app, "b1:me"))
        await asyncio.sleep(0)
        await app.process_update(callback(app, "b1:me"))
        during = session_row(db)
        release.set()
        await settle()

        assert during is not None
        assert t("booking.session_cleared", "en") not in [e.text for e in app.bot.edits]
        assert app.bot.edits[-1].text.startswith(
            t(
                "booking.success",
                "en",
                process_id="P-1",
                time=LONG_TIME,
                name=NAME,
                email=EMAIL,
            )
        )
        assert session_row(db) is None
