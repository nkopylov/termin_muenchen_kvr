# ABOUTME: Tests that every booking screen renders in the user's language, checked text for text.
# ABOUTME: Drives the real handlers with a FakeBot, an in-memory DB and a faked city API.

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session
from telegram.ext import ApplicationHandlerStop

from src.commands import booking
from src.repositories import BookingSessionRepository, UserRepository, WatchRepository
from src.watches.slots import SlotTime
from src.watches.when import PRESETS
from tests.conftest import NOW
from tests.fakes import FakeBot, FakeContext, make_callback_update, make_text_update

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("catalog", "clock", "today")]

USER_ID = 5151
MSG = 300
SERVICE_ID = 1063475
OFFICE_ID = 102526
BERLIN = ZoneInfo("Europe/Berlin")
TS = int(datetime(2026, 10, 29, 9, 30, tzinfo=BERLIN).timestamp())
TS_SINGLE_DIGIT_DAY = int(datetime(2026, 11, 5, 9, 5, tzinfo=BERLIN).timestamp())
NAME = "Ivan Petrov"
EMAIL = "ivan@example.com"
LANGS = ["en", "ru"]

CANCEL = {"en": "❌ Cancel", "ru": "❌ Отмена"}
CANCEL_BOOKING = {"en": "❌ Cancel", "ru": "❌ Отмена"}
CONFIRM = {"en": "✅ Confirm booking", "ru": "✅ Подтвердить запись"}
LONG_TIME = {
    "en": "09:30 on Thursday, October 29, 2026",
    "ru": "четверг, 29 октября 2026, 09:30",
}


@pytest.fixture
def bot():
    return FakeBot()


@pytest.fixture
def context(bot):
    return FakeContext(bot)


@pytest.fixture(autouse=True)
def boundaries(monkeypatch, events):
    events.patch(booking)
    monkeypatch.setattr(booking, "increment_bookings_started", lambda: None)
    monkeypatch.setattr(booking, "increment_bookings_completed", lambda: None)


def add_user(db, lang):
    with Session(db) as session:
        UserRepository(session).create_user(
            user_id=USER_ID, username="tester", language=lang
        )


def add_watch(db, live=True):
    with Session(db) as session:
        watches = WatchRepository(session)
        rec, _ = watches.create_or_update(USER_ID, SERVICE_ID, None, PRESETS["asap"])
        if live:
            watches.set_live_alert(
                rec.id, USER_ID, MSG, "slots", frozenset(), frozenset(), "h"
            )
        return rec.id


def open_session(db, state, timestamp=TS, name=None, email=None, watch_id=None):
    with Session(db) as session:
        repo = BookingSessionRepository(session)
        repo.create_session(
            user_id=USER_ID,
            state=state,
            service_id=SERVICE_ID,
            office_id=OFFICE_ID,
            date="2026-10-29",
            captcha_token="",
            expires_at=NOW + timedelta(minutes=15),
            watch_id=watch_id,
            message_id=MSG,
        )
        repo.update_session(USER_ID, timestamp=timestamp, name=name, email=email)


async def press(handler, context, data):
    update = make_callback_update(data, USER_ID, MSG, bot=context.bot)
    try:
        await handler(update, context)
    except ApplicationHandlerStop:
        pass


async def type_text(handler, context, text):
    update = make_text_update(text, USER_ID, bot=context.bot, message_id=77)
    try:
        await handler(update, context)
    except ApplicationHandlerStop:
        pass


def buttons(markup) -> list[tuple[str, str]]:
    return [
        (b.text, b.callback_data or b.url)
        for row in markup.inline_keyboard
        for b in row
    ]


def toasts(bot):
    return [c.text for c in bot.calls_of("answer_callback_query") if c.text]


class TestBookTap:
    @pytest.mark.parametrize(
        ("lang", "fetching", "prompt"),
        [
            (
                "en",
                "📅 Selected date: Thu 29.10\n\nFetching available time slots...",
                "📅 Available time slots for Thu 29.10:\n\nPlease select a time:",
            ),
            (
                "ru",
                "📅 Выбранная дата: Чт 29.10\n\nЗагружаю свободное время...",
                "📅 Свободное время на Чт 29.10:\n\nВыберите время:",
            ),
        ],
    )
    async def test_shows_times(
        self, db, context, bot, fake_availability, lang, fetching, prompt
    ):
        add_user(db, lang)
        watch_id = add_watch(db)
        fake_availability.day_results = [(SlotTime(TS, OFFICE_ID),)]

        await press(booking.book_day, context, f"b1:{watch_id}:20261029")
        await context.drain()

        assert [e.text for e in bot.edits] == [fetching, prompt]
        assert buttons(bot.edits[-1].reply_markup) == [
            ("09:30 · Forstenrieder Allee", f"b1:t:{OFFICE_ID}:{TS}"),
            (CANCEL[lang], "b1:x"),
        ]

    @pytest.mark.parametrize(
        ("lang", "result", "expected"),
        [
            (
                "en",
                (),
                (
                    "😕 No free times left on Thu 29.10.\n\n"
                    "I'll keep watching and send you the updated free days."
                ),
            ),
            (
                "ru",
                (),
                (
                    "😕 На Чт 29.10 свободного времени больше нет.\n\n"
                    "Я продолжаю искать и пришлю обновлённый список свободных дней."
                ),
            ),
            (
                "en",
                None,
                (
                    "⚠️ I couldn't load the times for Thu 29.10 right now.\n\n"
                    "I'll keep watching and send you the updated free days."
                ),
            ),
            (
                "ru",
                None,
                (
                    "⚠️ Сейчас не удалось загрузить время на Чт 29.10.\n\n"
                    "Я продолжаю искать и пришлю обновлённый список свободных дней."
                ),
            ),
        ],
    )
    async def test_no_times(
        self, db, context, bot, fake_availability, lang, result, expected
    ):
        add_user(db, lang)
        watch_id = add_watch(db)
        fake_availability.day_results = [result]

        await press(booking.book_day, context, f"b1:{watch_id}:20261029")
        await context.drain()

        assert bot.edits[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "result", "expected"),
        [
            ("en", (), "😕 No free times left on Thu 29.10."),
            ("ru", (), "😕 На Чт 29.10 свободного времени больше нет."),
            ("en", None, "⚠️ I couldn't load the times for Thu 29.10 right now."),
            ("ru", None, "⚠️ Сейчас не удалось загрузить время на Чт 29.10."),
        ],
    )
    async def test_no_times_without_a_watch_promises_nothing(
        self, db, context, bot, fake_availability, lang, result, expected
    ):
        add_user(db, lang)
        fake_availability.day_results = [result]

        await press(booking.book_legacy, context, "book_2026-10-29_10461_10339028")
        await context.drain()

        assert bot.edits[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "This watch has ended. Start a new search with 🔎 Find a Termin."),
            ("ru", "Этот поиск уже завершён. Начните новый через 🔎 Найти запись."),
        ],
    )
    async def test_ended_watch_toast(self, db, context, bot, lang, expected):
        add_user(db, lang)

        await press(booking.book_day, context, "b1:99:20261029")

        assert toasts(bot) == [expected]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "❌ Invalid booking data. Please try again."),
            ("ru", "❌ Некорректные данные записи. Пожалуйста, попробуйте снова."),
        ],
    )
    async def test_invalid_legacy_data_toast(self, db, context, bot, lang, expected):
        add_user(db, lang)

        await press(booking.book_legacy, context, "book_2026-13-01_10461_10339028")

        assert toasts(bot) == [expected]


class TestTimeSelected:
    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "✅ Selected time: Thu 29.10, 09:30\n\n"
                    "Please enter your full name (as it appears on your documents):"
                ),
            ),
            (
                "ru",
                (
                    "✅ Выбранное время: Чт 29.10, 09:30\n\n"
                    "Введите имя и фамилию (как в документах):"
                ),
            ),
        ],
    )
    async def test_asks_for_name(self, db, context, bot, lang, expected):
        add_user(db, lang)
        open_session(db, "SELECTING_TIME", timestamp=None)

        await press(booking.time_selected, context, f"b1:t:{OFFICE_ID}:{TS}")

        assert bot.edits[-1].text == expected
        assert buttons(bot.edits[-1].reply_markup) == [(CANCEL_BOOKING[lang], "b1:x")]

    @pytest.mark.parametrize(
        ("lang", "expected", "labels"),
        [
            (
                "en",
                (
                    "🕐 09:30 on Thursday, October 29, 2026\n"
                    "📍 Forstenrieder Allee\n\n"
                    "Book with your saved details?\n"
                    "👤 Ivan Petrov\n"
                    "📧 ivan@example.com"
                ),
                ["✅ Yes, book it", "✏️ Enter other details", "❌ Cancel"],
            ),
            (
                "ru",
                (
                    "🕐 четверг, 29 октября 2026, 09:30\n"
                    "📍 Forstenrieder Allee\n\n"
                    "Записаться с сохранёнными данными?\n"
                    "👤 Ivan Petrov\n"
                    "📧 ivan@example.com"
                ),
                ["✅ Да, записаться", "✏️ Ввести другие данные", "❌ Отмена"],
            ),
        ],
    )
    async def test_offers_saved_contact(self, db, context, bot, lang, expected, labels):
        add_user(db, lang)
        with Session(db) as session:
            UserRepository(session).set_booking_contact(USER_ID, NAME, EMAIL)
        open_session(db, "SELECTING_TIME", timestamp=None)

        await press(booking.time_selected, context, f"b1:t:{OFFICE_ID}:{TS}")

        assert bot.edits[-1].text == expected
        assert [text for text, _ in buttons(bot.edits[-1].reply_markup)] == labels


class TestNameReceived:
    @pytest.mark.parametrize(
        ("lang", "text", "expected"),
        [
            (
                "en",
                "Ivan",
                (
                    "❌ Please enter your full name (first and last name).\n\n"
                    "Example: John Smith"
                ),
            ),
            (
                "ru",
                "Ivan",
                "❌ Пожалуйста, введите имя и фамилию.\n\nПример: Ivan Petrov",
            ),
            ("en", "I P", "❌ Name is too short. Please enter your full name:"),
            (
                "ru",
                "I P",
                "❌ Имя слишком короткое. Пожалуйста, введите имя и фамилию:",
            ),
        ],
    )
    async def test_invalid(self, db, context, bot, lang, text, expected):
        add_user(db, lang)
        open_session(db, "ASKING_NAME")

        await type_text(booking.name_received, context, text)

        assert [s.text for s in bot.sent] == [expected]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "✅ Name: Ivan Petrov\n\n"
                    "Please enter your email address (you'll receive a confirmation "
                    "email):"
                ),
            ),
            (
                "ru",
                (
                    "✅ Имя: Ivan Petrov\n\n"
                    "Введите ваш адрес электронной почты (на него придёт письмо "
                    "с подтверждением):"
                ),
            ),
        ],
    )
    async def test_asks_for_email(self, db, context, bot, lang, expected):
        add_user(db, lang)
        open_session(db, "ASKING_NAME")

        await type_text(booking.name_received, context, NAME)

        [sent] = bot.sent
        assert sent.text == expected
        assert buttons(sent.reply_markup) == [(CANCEL_BOOKING[lang], "b1:x")]


class TestEmailReceived:
    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ Invalid email address. Please enter a valid email:\n\n"
                    "Example: your.name@example.com"
                ),
            ),
            (
                "ru",
                (
                    "❌ Некорректный адрес электронной почты. Пожалуйста, введите "
                    "правильный адрес:\n\nПример: your.name@example.com"
                ),
            ),
        ],
    )
    async def test_invalid_email(self, db, context, bot, lang, expected):
        add_user(db, lang)
        open_session(db, "ASKING_EMAIL", name=NAME)

        await type_text(booking.email_received, context, "not-an-email")

        assert [s.text for s in bot.sent] == [expected]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "📋 <b>Please confirm your booking:</b>\n\n"
                    "🕐 Time: 09:30 on Thursday, October 29, 2026\n"
                    "👤 Name: Ivan Petrov\n"
                    "📧 Email: ivan@example.com\n\n"
                    "<b>Important:</b> You will receive a confirmation email. "
                    "You MUST click the link in that email to finalize your "
                    "appointment!"
                ),
            ),
            (
                "ru",
                (
                    "📋 <b>Пожалуйста, подтвердите запись:</b>\n\n"
                    "🕐 Время: четверг, 29 октября 2026, 09:30\n"
                    "👤 Имя: Ivan Petrov\n"
                    "📧 Эл. почта: ivan@example.com\n\n"
                    "<b>Важно:</b> вам придёт письмо с подтверждением. "
                    "Обязательно перейдите по ссылке в этом письме, чтобы "
                    "окончательно подтвердить запись!"
                ),
            ),
        ],
    )
    async def test_confirmation_summary(self, db, context, bot, lang, expected):
        add_user(db, lang)
        open_session(db, "ASKING_EMAIL", name=NAME)

        await type_text(booking.email_received, context, EMAIL)

        [sent] = bot.sent
        assert sent.text == expected
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [
            (CONFIRM[lang], "b1:ok"),
            (CANCEL[lang], "b1:x"),
        ]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "🕐 Time: 09:05 on Thursday, November 5, 2026\n"),
            ("ru", "🕐 Время: четверг, 5 ноября 2026, 09:05\n"),
        ],
    )
    async def test_single_digit_day(self, db, context, bot, lang, expected):
        add_user(db, lang)
        open_session(db, "ASKING_EMAIL", timestamp=TS_SINGLE_DIGIT_DAY, name=NAME)

        await type_text(booking.email_received, context, EMAIL)

        assert expected in bot.sent[-1].text


@pytest.fixture
def city(monkeypatch):
    results = []

    async def book_appointment(**kwargs):
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(booking.booking_api, "book_appointment", book_appointment)
    return results


SUCCESS = {
    "en": (
        "🎉 <b>Booking successful!</b> 🎉\n\n"
        "📋 Booking ID: P-42\n"
        "🕐 Time: 09:30 on Thursday, October 29, 2026\n"
        "👤 Name: Ivan Petrov\n"
        "📧 Email: ivan@example.com\n\n"
        "<b>⚠️ IMPORTANT - Next Steps:</b>\n\n"
        "1. Check your email inbox at <b>ivan@example.com</b>\n"
        "2. Look for a confirmation email from the City of Munich "
        "(Landeshauptstadt München)\n"
        "3. <b>Click the confirmation link</b> in that email\n"
        "4. Your appointment will only be finalized after email confirmation\n\n"
        "If you don't see the email within 5 minutes, check your spam folder."
    ),
    "ru": (
        "🎉 <b>Запись оформлена!</b> 🎉\n\n"
        "📋 Номер записи: P-42\n"
        "🕐 Время: четверг, 29 октября 2026, 09:30\n"
        "👤 Имя: Ivan Petrov\n"
        "📧 Эл. почта: ivan@example.com\n\n"
        "<b>⚠️ ВАЖНО — что делать дальше:</b>\n\n"
        "1. Проверьте почтовый ящик <b>ivan@example.com</b>\n"
        "2. Найдите письмо с подтверждением от города Мюнхена "
        "(Landeshauptstadt München)\n"
        "3. <b>Перейдите по ссылке для подтверждения</b> в этом письме\n"
        "4. Запись будет окончательно оформлена только после подтверждения "
        "по электронной почте\n\n"
        "Если письмо не пришло в течение 5 минут, проверьте папку «Спам»."
    ),
}
FINISHED = {
    "en": "✅ I've stopped watching Address registration (Anmeldung) for you.",
    "ru": "✅ Поиск «Регистрация по адресу (Anmeldung)» завершён.",
}
FAILED = {
    "en": (
        "❌ <b>Booking failed</b>\n\n"
        "The appointment could not be booked. Possible reasons:\n"
        "• The slot was just taken by someone else\n"
        "• The city website did not respond\n\n"
        "Please try booking another available slot."
    ),
    "ru": (
        "❌ <b>Запись не удалась</b>\n\n"
        "Не удалось оформить запись. Возможные причины:\n"
        "• это время только что занял кто-то другой\n"
        "• сайт города не ответил\n\n"
        "Пожалуйста, попробуйте выбрать другое свободное время."
    ),
}
WILL_UPDATE = {
    "en": "I'll keep watching and send you the current free slots.",
    "ru": "Я продолжаю искать и пришлю актуальные свободные записи.",
}
ERROR = {
    "en": (
        "❌ Something went wrong while booking.\n\n"
        "Please try again or choose another free slot."
    ),
    "ru": (
        "❌ При оформлении записи что-то пошло не так.\n\n"
        "Пожалуйста, попробуйте снова или выберите другое свободное время."
    ),
}


class TestConfirmBooking:
    @pytest.mark.parametrize(
        ("lang", "processing"),
        [
            ("en", "⏳ Processing your booking...\nThis may take a few seconds."),
            ("ru", "⏳ Оформляю запись...\nЭто может занять несколько секунд."),
        ],
    )
    async def test_success_from_a_watch(self, db, context, bot, city, lang, processing):
        add_user(db, lang)
        watch_id = add_watch(db, live=False)
        open_session(db, "CONFIRMING", name=NAME, email=EMAIL, watch_id=watch_id)
        city.append({"processId": "P-42"})

        await press(booking.confirm, context, "b1:ok")
        await context.drain()

        assert [e.text for e in bot.edits] == [
            processing,
            SUCCESS[lang] + "\n\n" + FINISHED[lang],
        ]
        assert bot.edits[-1].parse_mode == "HTML"
        assert bot.edits[-1].reply_markup is None

    @pytest.mark.parametrize("lang", LANGS)
    async def test_success_without_a_watch(self, db, context, bot, city, lang):
        add_user(db, lang)
        open_session(db, "CONFIRMING", name=NAME, email=EMAIL)
        city.append({"processId": "P-42"})

        await press(booking.confirm, context, "b1:ok")
        await context.drain()

        assert bot.edits[-1].text == SUCCESS[lang]

    @pytest.mark.parametrize("lang", LANGS)
    async def test_failure(self, db, context, bot, city, lang):
        add_user(db, lang)
        watch_id = add_watch(db, live=False)
        open_session(db, "CONFIRMING", name=NAME, email=EMAIL, watch_id=watch_id)
        city.append(None)

        await press(booking.confirm, context, "b1:ok")
        await context.drain()

        assert bot.edits[-1].text == FAILED[lang] + "\n\n" + WILL_UPDATE[lang]
        assert bot.edits[-1].reply_markup is None

    @pytest.mark.parametrize("lang", LANGS)
    async def test_error(self, db, context, bot, city, caplog, lang):
        add_user(db, lang)
        open_session(db, "CONFIRMING", name=NAME, email=EMAIL)
        city.append(RuntimeError("boom <1>"))

        await press(booking.confirm, context, "b1:ok")
        await context.drain()

        assert bot.edits[-1].text == ERROR[lang]
        assert [
            r.getMessage() for r in caplog.records if r.name == booking.__name__
        ] == ["Booking error: boom <1>"]


class TestCancelAndCleared:
    @pytest.mark.parametrize(
        ("lang", "expected"),
        [("en", "❌ Booking cancelled."), ("ru", "❌ Запись отменена.")],
    )
    async def test_cancel(self, db, context, bot, lang, expected):
        add_user(db, lang)
        open_session(db, "ASKING_NAME")

        await press(booking.cancel, context, "b1:x")

        assert bot.edits[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ Your booking session expired or was cleared.\n\n"
                    "Please start a new booking from a Free slots message."
                ),
            ),
            (
                "ru",
                (
                    "❌ Время на оформление записи истекло, или процесс был сброшен.\n\n"
                    "Пожалуйста, начните запись заново из сообщения "
                    "«Есть свободные записи»."
                ),
            ),
        ],
    )
    async def test_session_cleared(self, db, context, bot, lang, expected):
        add_user(db, lang)

        await press(booking.booking_orphan_callback, context, "b1:ok")

        assert bot.edits[-1].text == expected
