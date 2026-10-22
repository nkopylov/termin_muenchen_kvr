# ABOUTME: Tests for appointment notification texts in English and Russian.
# ABOUTME: The Telegram bot and the city slots API are stubbed; user languages come from an in-memory DB.

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session

from src import database
from src.repositories import UserRepository
from src.services import notification_service
from src.services.notification_service import (
    format_available_appointments,
    notify_users_of_appointment,
)

EN_USER = 101
RU_USER = 202
SERVICE_ID = 10339027
OFFICE_ID = 10461
SERVICE_NAME = "Aufenthaltserlaubnis & Blue Card"
BOOKING_URL = (
    "https://stadt.muenchen.de/buergerservice/terminvereinbarung.html"
    f"#/services/{SERVICE_ID}/locations/{OFFICE_ID}"
)
DATES = [f"2026-12-{day:02d}" for day in range(1, 8)]


def days(dates: list[str]) -> list[dict]:
    return [{"date": d, "providerIDs": str(OFFICE_ID), "offices": []} for d in dates]


def ts(date: str, hhmm: str) -> int:
    return int(
        datetime.fromisoformat(f"{date}T{hhmm}")
        .replace(tzinfo=ZoneInfo("Europe/Berlin"))
        .timestamp()
    )


class TestFormatAvailableAppointments:
    def test_english_default_unchanged(self):
        data = {
            "availableDays": days(DATES),
            "slots_by_date": {"2026-12-01": ["09:00", "09:30"], "2026-12-02": []},
        }
        assert format_available_appointments(data) == (
            "📅 2026-12-01: 09:00, 09:30\n📅 2026-12-02\n... and 5 more days"
        )

    def test_english_days_without_slots_unchanged(self):
        data = {"availableDays": days(DATES[:6]) + [{"providerIDs": "1"}]}
        assert format_available_appointments(data, "en") == (
            "📅 2026-12-01\n📅 2026-12-02\n📅 2026-12-03\n📅 2026-12-04\n"
            "📅 2026-12-05\n... and 2 more days"
        )

    def test_english_single_remaining_day_keeps_wording(self):
        data = {"availableDays": days(DATES[:6])}
        assert format_available_appointments(data, "en").endswith("... and 1 more days")

    @pytest.mark.parametrize(
        ("total", "tail"),
        [
            (6, "... и ещё 1 день"),
            (7, "... и ещё 2 дня"),
            (10, "... и ещё 5 дней"),
            (16, "... и ещё 11 дней"),
            (26, "... и ещё 21 день"),
        ],
    )
    def test_russian_remaining_days_plural(self, total, tail):
        dates = [f"2027-01-{day:02d}" for day in range(1, total + 1)]
        data = {"availableDays": days(dates)}
        assert format_available_appointments(data, "ru") == (
            "\n".join(f"📅 {d}" for d in dates[:5]) + "\n" + tail
        )

    def test_russian_with_slots(self):
        data = {
            "availableDays": days(DATES[:3]),
            "slots_by_date": {"2026-12-01": ["09:00"], "2026-12-02": ["10:15"]},
        }
        assert format_available_appointments(data, "ru") == (
            "📅 2026-12-01: 09:00\n📅 2026-12-02: 10:15\n... и ещё 1 день"
        )

    @pytest.mark.parametrize(
        ("lang", "label"), [("en", "Unknown date"), ("ru", "Дата неизвестна")]
    )
    def test_day_without_date(self, lang, label):
        data = {"availableDays": [{"providerIDs": "1"}]}
        assert format_available_appointments(data, lang) == f"📅 {label}"


@pytest.fixture
def db(monkeypatch, db_engine):
    monkeypatch.setattr(database, "_engine", db_engine)
    with Session(db_engine) as session:
        repo = UserRepository(session)
        repo.create_user(user_id=EN_USER, language="en")
        repo.create_user(user_id=RU_USER, language="ru")
    return db_engine


@pytest.fixture
def events(monkeypatch):
    recorded: list[str] = []

    async def record(event_name, user_id=None, **properties):
        recorded.append(event_name)

    monkeypatch.setattr(notification_service, "track_event", record)
    return recorded


@pytest.fixture
def slots_api(monkeypatch):
    times = {
        "2026-12-01": ["09:00", "09:30"],
        "2026-12-02": ["14:45"],
    }

    def get_available_slots(date, office_id, service_id, captcha_token):
        if date not in times:
            return None
        appointments = [ts(date, hhmm) for hhmm in times[date]]
        return {"offices": [{"officeId": int(office_id), "appointments": appointments}]}

    monkeypatch.setattr(
        notification_service, "get_available_slots", get_available_slots
    )


def make_application():
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=lambda chat_id, **kw: SimpleNamespace(message_id=chat_id * 10)
        ),
        edit_message_text=AsyncMock(),
    )
    return SimpleNamespace(bot=bot, bot_data={})


async def notify(app, available_dates):
    await notify_users_of_appointment(
        app,
        [EN_USER, RU_USER],
        SERVICE_ID,
        OFFICE_ID,
        SERVICE_NAME,
        {"availableDays": days(available_dates)},
        "captcha",
    )


def sent_to(mock, user_id) -> dict:
    calls = [c.kwargs for c in mock.await_args_list if c.kwargs["chat_id"] == user_id]
    assert len(calls) == 1
    return calls[0]


def buttons(markup) -> list[tuple[str, str | None, str | None]]:
    return [
        (b.text, b.callback_data, b.url) for row in markup.inline_keyboard for b in row
    ]


@pytest.mark.asyncio
class TestNotifyUsersOfAppointment:
    async def test_initial_message_per_language(self, db, events, slots_api):
        app = make_application()
        await notify(app, DATES)

        en_dates = "\n".join(f"📅 {d}" for d in DATES[:5]) + "\n... and 2 more days"
        assert sent_to(app.bot.send_message, EN_USER)["text"] == (
            "🎉 <b>APPOINTMENT AVAILABLE!</b> 🎉\n\n"
            f"<b>{SERVICE_NAME}</b>\n\n"
            f"Available appointments:\n{en_dates}\n\n"
            f"🔗 <a href='{BOOKING_URL}'>Book appointment now!</a>\n\n"
            "⏳ Loading time slots..."
        )

        ru_dates = "\n".join(f"📅 {d}" for d in DATES[:5]) + "\n... и ещё 2 дня"
        assert sent_to(app.bot.send_message, RU_USER)["text"] == (
            "🎉 <b>ЕСТЬ СВОБОДНАЯ ЗАПИСЬ!</b> 🎉\n\n"
            f"<b>{SERVICE_NAME}</b>\n\n"
            f"Свободные записи:\n{ru_dates}\n\n"
            f"🔗 <a href='{BOOKING_URL}'>Записаться сейчас!</a>\n\n"
            "⏳ Загружаю свободное время..."
        )

    async def test_final_message_and_buttons_per_language(self, db, events, slots_api):
        app = make_application()
        await notify(app, DATES[:3])

        en_edit = sent_to(app.bot.edit_message_text, EN_USER)
        assert en_edit["message_id"] == EN_USER * 10
        assert en_edit["text"] == (
            "🎉 <b>APPOINTMENT AVAILABLE!</b> 🎉\n\n"
            f"<b>{SERVICE_NAME}</b>\n\n"
            "Available appointments:\n"
            "📅 2026-12-01: 09:00, 09:30\n📅 2026-12-02: 14:45\n📅 2026-12-03\n\n"
            f"🔗 <a href='{BOOKING_URL}'>Book appointment now!</a>\n\n"
            "⚡ Act fast - Appointments fill up quickly!"
        )
        assert buttons(en_edit["reply_markup"]) == [
            (f"📅 Book: {d}", f"book_{d}_{OFFICE_ID}_{SERVICE_ID}", None)
            for d in DATES[:3]
        ] + [("🔗 Book manually on website", None, BOOKING_URL)]

        ru_edit = sent_to(app.bot.edit_message_text, RU_USER)
        assert ru_edit["message_id"] == RU_USER * 10
        assert ru_edit["text"] == (
            "🎉 <b>ЕСТЬ СВОБОДНАЯ ЗАПИСЬ!</b> 🎉\n\n"
            f"<b>{SERVICE_NAME}</b>\n\n"
            "Свободные записи:\n"
            "📅 2026-12-01: 09:00, 09:30\n📅 2026-12-02: 14:45\n📅 2026-12-03\n\n"
            f"🔗 <a href='{BOOKING_URL}'>Записаться сейчас!</a>\n\n"
            "⚡ Поторопитесь — записи быстро разбирают!"
        )
        assert buttons(ru_edit["reply_markup"]) == [
            (f"📅 Записаться: {d}", f"book_{d}_{OFFICE_ID}_{SERVICE_ID}", None)
            for d in DATES[:3]
        ] + [("🔗 Записаться вручную на сайте", None, BOOKING_URL)]

    async def test_final_message_lists_remaining_days_in_russian(
        self, db, events, slots_api
    ):
        app = make_application()
        await notify(app, DATES)

        ru_text = sent_to(app.bot.edit_message_text, RU_USER)["text"]
        assert "📅 2026-12-05\n... и ещё 2 дня\n\n" in ru_text
        en_text = sent_to(app.bot.edit_message_text, EN_USER)["text"]
        assert "📅 2026-12-05\n... and 2 more days\n\n" in en_text

    async def test_user_without_language_gets_english(self, db, events, slots_api):
        with Session(db) as session:
            UserRepository(session).create_user(user_id=303, language="")
        app = make_application()
        await notify_users_of_appointment(
            app,
            [303],
            SERVICE_ID,
            OFFICE_ID,
            SERVICE_NAME,
            {"availableDays": days(DATES[:1])},
            "captcha",
        )
        assert sent_to(app.bot.send_message, 303)["text"].startswith(
            "🎉 <b>APPOINTMENT AVAILABLE!</b> 🎉"
        )
        assert (
            buttons(sent_to(app.bot.edit_message_text, 303)["reply_markup"])[0][0]
            == f"📅 Book: {DATES[0]}"
        )
