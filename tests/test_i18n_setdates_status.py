# ABOUTME: Tests that /setdates and /status reply in the user's language (English and Russian).
# ABOUTME: Telegram objects are stubbed at the boundary; DB state is real in-memory SQLite.

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from src import database
from src.commands import setdates as setdates_module
from src.commands.setdates import setdates_command
from src.commands.status import status_command
from src.config import get_config
from src.db_models import AppointmentLog, User
from src.repositories import SubscriptionRepository, UserRepository
from src.services import appointment_checker

pytestmark = pytest.mark.asyncio

USER_ID = 5150


@dataclass
class Sent:
    text: str
    reply_markup: object = None
    parse_mode: str | None = None


@dataclass
class FakeMessage:
    replies: list[Sent] = field(default_factory=list)

    async def reply_text(self, text, reply_markup=None, parse_mode=None, **kwargs):
        self.replies.append(Sent(text, reply_markup, parse_mode))


def make_update():
    message = FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=USER_ID, language_code="en"),
        message=message,
        effective_message=message,
    )


def make_context(args=None, user_data=None):
    return SimpleNamespace(
        args=[] if args is None else args,
        user_data={} if user_data is None else user_data,
    )


def buttons(markup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def add_user(db, language, start_date=None, end_date=None):
    with Session(db) as session:
        UserRepository(session).create_user(user_id=USER_ID, language=language)
        if start_date:
            UserRepository(session).set_date_range(USER_ID, start_date, end_date)


@pytest.fixture(autouse=True)
def db(monkeypatch, db_engine):
    monkeypatch.setattr(database, "_engine", db_engine)
    return db_engine


@pytest.fixture(autouse=True)
def events(monkeypatch):
    recorded: list[tuple[str, dict]] = []

    async def record(event_name, user_id=None, **properties):
        recorded.append((event_name, {"user_id": user_id, **properties}))

    monkeypatch.setattr(setdates_module, "track_event", record)
    return recorded


async def run_setdates(args, user_data=None):
    update = make_update()
    await setdates_command(update, make_context(args, user_data))
    assert len(update.message.replies) == 1
    return update.message.replies[0]


async def run_status(user_data=None):
    update = make_update()
    await status_command(update, make_context(user_data=user_data))
    assert len(update.message.replies) == 1
    return update.message.replies[0]


def preset_dates():
    today = datetime.now()
    return today.strftime("%Y-%m-%d"), [
        (today + timedelta(days=d)).strftime("%Y-%m-%d") for d in (2, 7, 30, 90, 180)
    ]


EN_PRESETS_TEXT = (
    "📅 <b>Set Date Range</b>\n\n"
    "Choose a preset date range or use a custom range:\n\n"
    "<b>Custom Range:</b>\n"
    "<code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
    "Example: <code>/setdates 2025-10-01 2025-10-31</code>"
)
EN_INVALID_FORMAT = (
    "❌ Invalid format.\n\n"
    "Usage: <code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
    "Example:\n"
    "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
    "Or use /setdates without arguments for quick presets."
)
EN_INVALID_RANGE = (
    "❌ Invalid date range. End date must be after start date.\n\n"
    "Example: <code>/setdates 2025-10-01 2025-10-31</code>"
)
EN_INVALID_DATE = (
    "❌ Invalid date format. Please use YYYY-MM-DD\n\n"
    "Example: <code>/setdates 2025-10-01 2025-10-31</code>"
)


class TestSetdatesPresets:
    async def test_english_unchanged(self, db):
        add_user(db, "en")
        sent = await run_setdates([])
        today, (d2, d7, d30, d90, d180) = preset_dates()
        assert sent.text == EN_PRESETS_TEXT
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [
            (f"📅 Next 2 days ({today} to {d2})", "setdates:2"),
            (f"📅 Next week ({today} to {d7})", "setdates:7"),
            (f"📅 Next 30 days ({today} to {d30})", "setdates:30"),
            (f"📅 Next 3 months ({today} to {d90})", "setdates:90"),
            (f"📅 Next 6 months ({today} to {d180})", "setdates:180"),
            ("🏠 Main Menu", "main_menu"),
        ]

    async def test_russian(self, db):
        add_user(db, "ru")
        sent = await run_setdates([])
        today, (d2, d7, d30, d90, d180) = preset_dates()
        assert sent.text == (
            "📅 <b>Выбор периода дат</b>\n\n"
            "Выберите готовый период или укажите свой:\n\n"
            "<b>Свой период:</b>\n"
            "<code>/setdates ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>\n\n"
            "Пример: <code>/setdates 2025-10-01 2025-10-31</code>"
        )
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [
            (f"📅 Ближайшие 2 дня ({today} — {d2})", "setdates:2"),
            (f"📅 Ближайшая неделя ({today} — {d7})", "setdates:7"),
            (f"📅 Ближайшие 30 дней ({today} — {d30})", "setdates:30"),
            (f"📅 Ближайшие 3 месяца ({today} — {d90})", "setdates:90"),
            (f"📅 Ближайшие 6 месяцев ({today} — {d180})", "setdates:180"),
            ("🏠 Главное меню", "main_menu"),
        ]

    async def test_cached_language_is_used(self, db):
        add_user(db, "en")
        sent = await run_setdates([], user_data={"lang": "ru"})
        assert sent.text.startswith("📅 <b>Выбор периода дат</b>")


class TestSetdatesValidation:
    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            (["2025-10-01"], EN_INVALID_FORMAT),
            (["2025-10-31", "2025-10-01"], EN_INVALID_RANGE),
            (["2025-10-01", "2025-10-01"], EN_INVALID_RANGE),
            (["01.10.2025", "2025-10-31"], EN_INVALID_DATE),
        ],
    )
    async def test_english_unchanged(self, db, args, expected):
        add_user(db, "en")
        sent = await run_setdates(args)
        assert sent.text == expected
        assert sent.parse_mode == "HTML"

    async def test_russian_invalid_format(self, db):
        add_user(db, "ru")
        sent = await run_setdates(["a", "b", "c"])
        assert sent.text == (
            "❌ Неверный формат.\n\n"
            "Правильно так: <code>/setdates ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>\n\n"
            "Пример:\n"
            "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
            "Или отправьте /setdates без параметров, чтобы выбрать готовый период."
        )
        assert sent.parse_mode == "HTML"

    async def test_russian_invalid_range(self, db):
        add_user(db, "ru")
        sent = await run_setdates(["2025-10-31", "2025-10-01"])
        assert sent.text == (
            "❌ Неверный период дат. Дата окончания должна быть позже даты начала.\n\n"
            "Пример: <code>/setdates 2025-10-01 2025-10-31</code>"
        )

    async def test_russian_invalid_date(self, db):
        add_user(db, "ru")
        sent = await run_setdates(["2025-13-01", "2025-10-31"])
        assert sent.text == (
            "❌ Неверный формат даты. Укажите дату в виде ГГГГ-ММ-ДД.\n\n"
            "Пример: <code>/setdates 2025-10-01 2025-10-31</code>"
        )

    async def test_invalid_input_does_not_store(self, db):
        add_user(db, "ru")
        await run_setdates(["2025-10-31", "2025-10-01"])
        with Session(db) as session:
            user = session.get(User, USER_ID)
            assert (user.start_date, user.end_date) == (None, None)


class TestSetdatesSuccess:
    async def test_english_unchanged(self, db, events):
        add_user(db, "en")
        sent = await run_setdates(["2025-10-01", "2025-10-31"])
        assert sent.text == (
            "✅ Date range updated!\n\n"
            "From: <b>2025-10-01</b>\n"
            "To: <b>2025-10-31</b>\n\n"
            "The bot will now search for appointments in this date range."
        )
        assert sent.parse_mode == "HTML"
        assert events == [
            (
                "date_range_set",
                {"user_id": USER_ID, "range_days": 30, "range_direction": "set"},
            )
        ]

    async def test_russian(self, db):
        add_user(db, "ru")
        sent = await run_setdates(["2025-10-01", "2025-10-31"])
        assert sent.text == (
            "✅ Период дат обновлён!\n\n"
            "Начало: <b>2025-10-01</b>\n"
            "Окончание: <b>2025-10-31</b>\n\n"
            "Теперь бот будет искать свободные записи в этот период."
        )
        with Session(db) as session:
            user = session.get(User, USER_ID)
            assert (user.start_date, user.end_date) == ("2025-10-01", "2025-10-31")


@pytest.fixture
def checker(monkeypatch):
    """Control the last check time and the configured check interval."""

    def configure(last_check_ago: timedelta | None, interval: int = 120):
        last = None if last_check_ago is None else datetime.now() - last_check_ago
        monkeypatch.setitem(appointment_checker.stats, "last_check_time", last)
        monkeypatch.setattr(get_config(), "check_interval", interval)

    return configure


def add_subscription(db, service_id=1, office_id=2):
    with Session(db) as session:
        SubscriptionRepository(session).add_subscription(USER_ID, service_id, office_id)


def add_log(db, found_ago: timedelta, service_id=1):
    with Session(db) as session:
        session.add(
            AppointmentLog(
                found_at=datetime.now() - found_ago,
                service_id=service_id,
                office_id=2,
                data="{}",
            )
        )
        session.commit()


class TestStatusNotRegistered:
    async def test_english_unchanged(self):
        sent = await run_status()
        assert sent.text == "❌ You are not registered.\n\nUse /start to register."

    async def test_russian_from_cache(self):
        sent = await run_status(user_data={"lang": "ru"})
        assert sent.text == (
            "❌ Вы не зарегистрированы.\n\nЧтобы зарегистрироваться, отправьте /start."
        )


class TestStatusScreen:
    async def test_english_unchanged(self, db, checker):
        add_user(db, "en", "2025-10-01", "2025-10-31")
        add_subscription(db)
        checker(timedelta(seconds=10))
        sent = await run_status()
        assert sent.text == (
            "📊 <b>Your Status</b>\n\n"
            f"👤 User ID: <code>{USER_ID}</code>\n"
            "📋 Subscriptions: <b>1</b>\n"
            "📅 Date Range: 2025-10-01 to 2025-10-31\n"
            "🌐 Language: 🇬🇧 English\n\n"
            "🔍 Last checked: 10 seconds ago\n"
            "⏱ Next check in: ~1 minutes\n"
            "⚙️ Check interval: 120 seconds"
            "\n🎯 Appointments found: 0"
        )
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [("🏠 Main Menu", "main_menu")]

    async def test_russian(self, db, checker):
        add_user(db, "ru", "2025-10-01", "2025-10-31")
        add_subscription(db)
        checker(timedelta(seconds=10))
        sent = await run_status()
        assert sent.text == (
            "📊 <b>Ваш статус</b>\n\n"
            f"👤 ID пользователя: <code>{USER_ID}</code>\n"
            "📋 Подписки: <b>1</b>\n"
            "📅 Период дат: 2025-10-01 — 2025-10-31\n"
            "🌐 Язык: 🇷🇺 Русский\n\n"
            "🔍 Последняя проверка: 10 секунд назад\n"
            "⏱ Следующая проверка: через ~1 минуту\n"
            "⚙️ Интервал проверки: 120 секунд"
            "\n🎯 Найдено записей: 0"
        )
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [("🏠 Главное меню", "main_menu")]

    async def test_unset_language_shows_english(self, db, checker):
        add_user(db, "")
        checker(None)
        sent = await run_status()
        assert "🌐 Language: 🇬🇧 English\n" in sent.text

    async def test_never_checked_english(self, db, checker):
        add_user(db, "en")
        checker(None)
        sent = await run_status()
        assert "🔍 Last checked: Never\n⏱ Next check in: Soon\n" in sent.text

    async def test_never_checked_russian(self, db, checker):
        add_user(db, "ru")
        checker(None)
        sent = await run_status()
        assert (
            "🔍 Последняя проверка: ещё не проводилась\n⏱ Следующая проверка: скоро\n"
            in sent.text
        )


class TestStatusTiming:
    @pytest.mark.parametrize(
        ("ago", "interval", "last", "next_"),
        [
            (timedelta(seconds=10), 120, "10 seconds ago", "~1 minutes"),
            (timedelta(seconds=118), 120, "1 minutes ago", "~1 seconds"),
            (timedelta(hours=2), 120, "2 hours ago", "~0 seconds"),
        ],
    )
    async def test_english_unchanged(self, db, checker, ago, interval, last, next_):
        add_user(db, "en")
        checker(ago, interval)
        sent = await run_status()
        assert f"🔍 Last checked: {last}\n⏱ Next check in: {next_}\n" in sent.text

    @pytest.mark.parametrize(
        ("ago", "interval", "last", "next_"),
        [
            (timedelta(seconds=1), 120, "1 секунду назад", "через ~1 минуту"),
            (timedelta(seconds=3), 600, "3 секунды назад", "через ~9 минут"),
            (timedelta(seconds=118), 120, "1 минуту назад", "через ~1 секунду"),
            (timedelta(seconds=100), 120, "1 минуту назад", "через ~19 секунд"),
            (timedelta(seconds=117), 120, "1 минуту назад", "через ~2 секунды"),
            (timedelta(minutes=3), 600, "3 минуты назад", "через ~6 минут"),
            (timedelta(minutes=5), 600, "5 минут назад", "через ~4 минуты"),
            (timedelta(minutes=21), 600, "21 минуту назад", "через ~0 секунд"),
            (timedelta(hours=1), 120, "1 час назад", "через ~0 секунд"),
            (timedelta(hours=2), 120, "2 часа назад", "через ~0 секунд"),
            (timedelta(hours=5), 120, "5 часов назад", "через ~0 секунд"),
        ],
    )
    async def test_russian_plurals(self, db, checker, ago, interval, last, next_):
        add_user(db, "ru")
        checker(ago, interval)
        sent = await run_status()
        assert (
            f"🔍 Последняя проверка: {last}\n⏱ Следующая проверка: {next_}\n"
            in sent.text
        )

    @pytest.mark.parametrize(
        ("interval", "expected"),
        [(120, "120 секунд"), (21, "21 секунда"), (22, "22 секунды")],
    )
    async def test_russian_interval_plurals(self, db, checker, interval, expected):
        add_user(db, "ru")
        checker(None, interval)
        sent = await run_status()
        assert f"⚙️ Интервал проверки: {expected}\n" in sent.text

    async def test_english_interval_unchanged(self, db, checker):
        add_user(db, "en")
        checker(None, 21)
        sent = await run_status()
        assert "⚙️ Check interval: 21 seconds\n" in sent.text


class TestStatusAppointmentsFound:
    @pytest.mark.parametrize(
        ("found_ago", "expected"),
        [
            (timedelta(minutes=1), "today"),
            (timedelta(days=1, hours=1), "yesterday"),
            (timedelta(days=5, hours=1), "5 days ago"),
        ],
    )
    async def test_english_unchanged(self, db, checker, found_ago, expected):
        add_user(db, "en")
        add_subscription(db)
        add_log(db, found_ago)
        add_log(db, timedelta(minutes=1), service_id=99)
        checker(None)
        sent = await run_status()
        assert sent.text.endswith(f"\n🎯 Appointments found: 1 (last: {expected})")

    @pytest.mark.parametrize(
        ("found_ago", "expected"),
        [
            (timedelta(minutes=1), "сегодня"),
            (timedelta(days=1, hours=1), "вчера"),
            (timedelta(days=2, hours=1), "2 дня назад"),
            (timedelta(days=5, hours=1), "5 дней назад"),
            (timedelta(days=21, hours=1), "21 день назад"),
            (timedelta(days=22, hours=1), "22 дня назад"),
        ],
    )
    async def test_russian(self, db, checker, found_ago, expected):
        add_user(db, "ru")
        add_subscription(db)
        add_log(db, found_ago)
        add_log(db, timedelta(days=40))
        checker(None)
        sent = await run_status()
        assert sent.text.endswith(f"\n🎯 Найдено записей: 2 (последняя: {expected})")
