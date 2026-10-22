# ABOUTME: Tests for plain text messages: service search results and typed date answers.
# ABOUTME: Real handlers against an in-memory DB, the test catalog, a fake availability API.

from datetime import date

import pytest
from sqlmodel import Session

from src.handlers.text_input import AWAIT_KEY, clear_pending_input, on_text
from src.i18n import t
from src.repositories import UserRepository, WatchRepository
from src.ui import callbacks as cb
from src.watches.availability import CallResult
from src.watches.when import PRESETS, WhenSpec
from tests.fakes import FakeContext, calendar, make_text_update

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db", "catalog", "today", "clock"),
]

USER = 4242
PROMPT = 40
TEXT_MSG = 41
PASSPORT = 1063453
ANMELDUNG = 1063475
FORSTENRIED = 102526


def register(db, lang="en"):
    with Session(db) as session:
        UserRepository(session).create_user(USER, language=lang)


def repo(db):
    return WatchRepository(Session(db))


def nav_pointer(db):
    with Session(db) as session:
        return UserRepository(session).get_nav_message_id(USER)


def set_nav_pointer(db, message_id):
    with Session(db) as session:
        UserRepository(session).set_nav_message_id(USER, message_id)


async def send_text(context, text):
    update = make_text_update(text, USER, bot=context.bot, message_id=TEXT_MSG)
    await on_text(update, context)


def awaiting(kind, watch_id=None, service_id=ANMELDUNG, office_id=FORSTENRIED):
    return {
        "kind": kind,
        "service_id": service_id,
        "office_id": office_id,
        "watch_id": watch_id,
        "prompt_msg_id": PROMPT,
    }


def strips(bot):
    return [c.message_id for c in bot.calls_of("edit_message_reply_markup")]


class TestSearch:
    async def test_results(self, db, context):
        register(db)
        await send_text(context, "passport")
        sent = context.bot.sent[-1]
        assert sent.text == t("find.results", "en", query="passport")
        layout = [
            [b.callback_data for b in row] for row in sent.reply_markup.inline_keyboard
        ]
        assert layout[0] == [cb.find_service(PASSPORT)]
        assert layout[-1] == [cb.find_all()]
        assert sent.reply_markup.inline_keyboard[0][0].text == t(
            f"watch.svc_{PASSPORT}", "en"
        )
        assert nav_pointer(db) == sent.message_id

    async def test_results_in_russian(self, db, context):
        register(db, "ru")
        await send_text(context, "паспорт")
        sent = context.bot.sent[-1]
        assert sent.text == t("find.results", "ru", query="паспорт")
        assert sent.reply_markup.inline_keyboard[0][0].text == t(
            f"watch.svc_{PASSPORT}", "ru"
        )

    async def test_at_most_eight_results(self, db, context, catalog):
        catalog["services"] += [
            {"id": 900 + i, "name": f"Amtsbescheinigung {i}"} for i in range(12)
        ]
        register(db)
        await send_text(context, "amtsbescheinigung")
        rows = context.bot.sent[-1].reply_markup.inline_keyboard
        assert len(rows) == 8 + 1

    async def test_nothing_found(self, db, context):
        register(db)
        await send_text(context, "xyzzy")
        sent = context.bot.sent[-1]
        assert sent.text == t("find.nothing", "en", query="xyzzy")
        assert [
            [b.callback_data for b in r] for r in sent.reply_markup.inline_keyboard
        ] == [[cb.find_all()]]

    async def test_too_short(self, db, context):
        register(db)
        await send_text(context, "a")
        assert context.bot.sent[-1].text == t("find.nothing", "en", query="a")

    async def test_query_is_html_escaped(self, db, context):
        register(db)
        await send_text(context, "<b>pass</b> & co")
        text = context.bot.sent[-1].text
        assert "&lt;b&gt;pass&lt;/b&gt; &amp; co" in text
        assert "<b>pass</b>" not in text

    async def test_long_query_is_truncated(self, db, context):
        register(db)
        await send_text(context, "x" * 100)
        assert context.bot.sent[-1].text == t("find.nothing", "en", query="x" * 60)

    async def test_unregistered_user(self, db, context):
        await send_text(context, "passport")
        assert context.bot.sent[-1].text == t("start.not_registered", "en")

    async def test_previous_nav_screen_is_stripped(self, db, context):
        register(db)
        set_nav_pointer(db, PROMPT)
        await send_text(context, "passport")
        assert strips(context.bot) == [PROMPT]


class TestTypedDates:
    @pytest.fixture
    def empty_calendar(self, fake_availability):
        fake_availability.calendar_results.append(CallResult(True, calendar(), None))
        return fake_availability

    @pytest.fixture
    def prompt(self, db):
        register(db)
        set_nav_pointer(db, PROMPT)

    @pytest.mark.usefixtures("prompt")
    async def test_valid_before_date_creates_watch(self, db, context, empty_calendar):
        context.user_data[AWAIT_KEY] = awaiting("before")
        await send_text(context, "15.11")

        assert AWAIT_KEY not in context.user_data
        sent = context.bot.sent[-1]
        assert strips(context.bot) == [PROMPT]
        assert nav_pointer(db) is None
        await context.drain()

        rec = repo(db).find_open(USER, ANMELDUNG)
        assert rec.when == WhenSpec("before", date_to=date(2026, 11, 15))
        assert rec.office_id == FORSTENRIED
        assert rec.live.message_id == sent.message_id

    @pytest.mark.usefixtures("prompt")
    @pytest.mark.parametrize(
        "text",
        ["1.11 bis 15.11", "2026-11-01 - 2026-11-15", "с 01.11.2026 до 15.11.2026"],
    )
    async def test_valid_range(self, db, context, empty_calendar, text):
        context.user_data[AWAIT_KEY] = awaiting("range")
        await send_text(context, text)
        await context.drain()
        rec = repo(db).find_open(USER, ANMELDUNG)
        assert rec.when == WhenSpec(
            "between", date_from=date(2026, 11, 1), date_to=date(2026, 11, 15)
        )

    @pytest.mark.usefixtures("prompt")
    async def test_range_for_existing_watch(self, db, context, empty_calendar):
        rec, _ = repo(db).create_or_update(USER, ANMELDUNG, None, PRESETS["asap"])
        context.user_data[AWAIT_KEY] = awaiting("range", watch_id=rec.id)
        await send_text(context, "01.11.2026 - 15.11.2026")
        await context.drain()
        updated = repo(db).get(rec.id)
        assert updated.when.kind == "between"
        assert updated.live.message_id == context.bot.sent[-1].message_id

    @pytest.mark.usefixtures("prompt")
    @pytest.mark.parametrize(
        ("kind", "text", "key"),
        [
            ("before", "31.02.2027", "find.date_format"),
            ("before", "15.11 or so 1", "find.date_format"),
            ("before", "01.10.2026", "find.date_past"),
            ("before", "22.10.2026", "find.date_past"),
            ("before", "2028-01-01", "find.date_too_far"),
            ("range", "15.11", "find.date_format"),
            ("range", "15.12 - 01.12", "find.date_order"),
            ("range", "01.09.2026 - 01.10.2026", "find.date_past"),
            ("range", "01.11.2026 - 01.01.2028", "find.date_too_far"),
        ],
    )
    async def test_errors(self, db, context, fake_availability, kind, text, key):
        context.user_data[AWAIT_KEY] = awaiting(kind)
        await send_text(context, text)

        sent = context.bot.sent[-1]
        assert sent.text == t(key, "en", max_date="21.10.2027")
        assert [
            [b.callback_data for b in r] for r in sent.reply_markup.inline_keyboard
        ] == [[cb.find_cancel()]]
        assert strips(context.bot) == [PROMPT]
        assert context.user_data[AWAIT_KEY]["prompt_msg_id"] == sent.message_id
        assert nav_pointer(db) == sent.message_id
        assert repo(db).find_open(USER, ANMELDUNG) is None
        assert fake_availability.calendar_calls == []

    @pytest.mark.usefixtures("prompt")
    async def test_error_then_valid_date(self, db, context, empty_calendar):
        context.user_data[AWAIT_KEY] = awaiting("before")
        await send_text(context, "40.40")
        error_msg = context.bot.sent[-1].message_id
        await send_text(context, "2026-12-01")
        await context.drain()
        assert strips(context.bot) == [PROMPT, error_msg]
        assert repo(db).find_open(USER, ANMELDUNG).when.date_to == date(2026, 12, 1)

    @pytest.mark.usefixtures("prompt")
    async def test_text_without_digits_searches(self, db, context):
        context.user_data[AWAIT_KEY] = awaiting("before")
        await send_text(context, "passport")
        assert AWAIT_KEY not in context.user_data
        assert context.bot.sent[-1].text == t("find.results", "en", query="passport")
        assert strips(context.bot) == [PROMPT]


class TestClearPendingInput:
    async def test_clears(self):
        context = FakeContext(user_data={AWAIT_KEY: {"kind": "before"}, "lang": "ru"})
        clear_pending_input(context)
        assert context.user_data == {"lang": "ru"}

    async def test_nothing_pending(self):
        context = FakeContext()
        clear_pending_input(context)
        assert context.user_data == {}
