# ABOUTME: Tests that every booking conversation screen renders in the user's language.
# ABOUTME: English output must match the original texts byte for byte; Russian is checked exactly.

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session
from telegram.ext import ConversationHandler

from src import database
from src.commands import booking
from src.commands.booking import (
    ASKING_EMAIL,
    ASKING_NAME,
    CONFIRMING,
    SELECTING_TIME,
    cancel_booking_button,
    cancel_booking_conversation,
    confirm_booking,
    create_booking_session,
    email_received,
    get_booking_session,
    name_received,
    start_booking,
    time_selected,
    update_booking_session,
)
from src.repositories import UserRepository

USER_ID = 5151
OFFICE_ID = 200
SERVICE_ID = 100
DATE = "2025-01-15"
BERLIN = ZoneInfo("Europe/Berlin")
TS = int(datetime(2025, 1, 15, 10, 30, tzinfo=BERLIN).timestamp())
TS_SINGLE_DIGIT_DAY = int(datetime(2025, 3, 5, 9, 5, tzinfo=BERLIN).timestamp())
NAME = "Ivan Petrov"
EMAIL = "ivan@example.com"
LANGS = ["en", "ru"]


@dataclass
class Sent:
    text: str
    reply_markup: object = None
    parse_mode: str | None = None


@dataclass
class FakeMessage:
    text: str | None = None
    replies: list[Sent] = field(default_factory=list)

    async def reply_text(self, text, reply_markup=None, parse_mode=None, **kwargs):
        self.replies.append(Sent(text, reply_markup, parse_mode))


@dataclass
class FakeQuery:
    data: str
    answers: list[tuple] = field(default_factory=list)
    edits: list[Sent] = field(default_factory=list)

    async def answer(self, *args, **kwargs):
        self.answers.append(args)

    async def edit_message_text(
        self, text, reply_markup=None, parse_mode=None, **kwargs
    ):
        self.edits.append(Sent(text, reply_markup, parse_mode))


def make_update(*, text=None, data=None):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=USER_ID),
        message=FakeMessage(text=text) if text is not None else None,
        callback_query=FakeQuery(data=data) if data is not None else None,
    )


def make_context(captcha_token="tok"):
    bot_data = {"captcha_token": captcha_token} if captcha_token else {}
    return SimpleNamespace(user_data={}, bot_data=bot_data)


def buttons(markup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


@pytest.fixture(autouse=True)
def db(monkeypatch, db_engine):
    monkeypatch.setattr(database, "_engine", db_engine)
    return db_engine


@pytest.fixture(autouse=True)
def boundaries(monkeypatch):
    async def record(event_name, user_id=None, **properties):
        return None

    monkeypatch.setattr(booking, "track_event", record)
    monkeypatch.setattr(booking, "get_service_info", lambda _id: {"name": "Svc"})


def add_user(db, lang):
    with Session(db) as session:
        UserRepository(session).create_user(
            user_id=USER_ID, username="tester", language=lang
        )


def open_session(timestamp=None, name=None, email=None, state="SELECTING_TIME"):
    create_booking_session(
        user_id=USER_ID,
        service_id=SERVICE_ID,
        office_id=OFFICE_ID,
        date=DATE,
        captcha_token="tok",
        state=state,
    )
    update_booking_session(USER_ID, timestamp=timestamp, name=name, email=email)


CANCEL = {"en": "❌ Cancel", "ru": "❌ Отмена"}
CANCEL_BOOKING = {"en": "❌ Cancel Booking", "ru": "❌ Отменить запись"}
CONFIRM = {"en": "✅ Confirm Booking", "ru": "✅ Подтвердить запись"}
MAIN_MENU = {"en": "🏠 Main Menu", "ru": "🏠 Главное меню"}
CANCELLED = {"en": "❌ Booking cancelled.", "ru": "❌ Запись отменена."}
SESSION_EXPIRED = {
    "en": "❌ Session expired. Please start again.",
    "ru": "❌ Сессия истекла. Пожалуйста, начните заново.",
}


@pytest.mark.asyncio
class TestStartBooking:
    @pytest.mark.parametrize(
        ("lang", "fetching", "prompt"),
        [
            (
                "en",
                "📅 Selected date: 2025-01-15\n\nFetching available time slots...",
                "📅 Available time slots for 2025-01-15:\n\nPlease select a time:",
            ),
            (
                "ru",
                "📅 Выбранная дата: 2025-01-15\n\nЗагружаю свободное время...",
                "📅 Свободное время на 2025-01-15:\n\nВыберите время:",
            ),
        ],
    )
    async def test_shows_time_slots(self, db, monkeypatch, lang, fetching, prompt):
        add_user(db, lang)
        monkeypatch.setattr(
            booking,
            "get_available_slots",
            lambda *a: {"offices": [{"officeId": OFFICE_ID, "appointments": [TS]}]},
        )
        update = make_update(data=f"book_{DATE}_{OFFICE_ID}_{SERVICE_ID}")

        state = await start_booking(update, make_context())

        assert state == SELECTING_TIME
        edits = update.callback_query.edits
        assert [e.text for e in edits] == [fetching, prompt]
        assert buttons(edits[-1].reply_markup) == [
            ("🕐 10:30", f"time_{TS}"),
            (CANCEL[lang], "cancel_booking"),
        ]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ Error: Captcha token expired. Please try again from the "
                    "appointment notification."
                ),
            ),
            (
                "ru",
                (
                    "❌ Ошибка: срок действия капчи истёк. Пожалуйста, попробуйте "
                    "снова из уведомления о свободной записи."
                ),
            ),
        ],
    )
    async def test_captcha_expired(self, db, lang, expected):
        add_user(db, lang)
        update = make_update(data=f"book_{DATE}_{OFFICE_ID}_{SERVICE_ID}")

        state = await start_booking(update, make_context(captcha_token=None))

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ No available time slots found for 2025-01-15.\n"
                    "They may have been booked already. Please try another date."
                ),
            ),
            (
                "ru",
                (
                    "❌ На 2025-01-15 свободного времени не найдено.\n"
                    "Возможно, его уже заняли. Пожалуйста, выберите другую дату."
                ),
            ),
        ],
    )
    async def test_no_slots_found(self, db, monkeypatch, lang, expected):
        add_user(db, lang)
        monkeypatch.setattr(booking, "get_available_slots", lambda *a: None)
        update = make_update(data=f"book_{DATE}_{OFFICE_ID}_{SERVICE_ID}")

        state = await start_booking(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "❌ No time slots available for 2025-01-15."),
            ("ru", "❌ На 2025-01-15 нет свободного времени."),
        ],
    )
    async def test_no_appointments_at_office(self, db, monkeypatch, lang, expected):
        add_user(db, lang)
        monkeypatch.setattr(
            booking,
            "get_available_slots",
            lambda *a: {"offices": [{"officeId": 999, "appointments": [TS]}]},
        )
        update = make_update(data=f"book_{DATE}_{OFFICE_ID}_{SERVICE_ID}")

        state = await start_booking(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "❌ Invalid booking data. Please try again."),
            ("ru", "❌ Некорректные данные записи. Пожалуйста, попробуйте снова."),
        ],
    )
    async def test_invalid_data(self, db, lang, expected):
        add_user(db, lang)
        update = make_update(data=f"book_{DATE}")

        state = await start_booking(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == expected


@pytest.mark.asyncio
class TestTimeSelected:
    @pytest.mark.parametrize("lang", LANGS)
    async def test_cancel(self, db, lang):
        add_user(db, lang)
        open_session()
        update = make_update(data="cancel_booking")

        state = await time_selected(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == CANCELLED[lang]
        assert get_booking_session(USER_ID) is None

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ Your booking session expired or was cleared.\n\n"
                    "Please start a new booking from an appointment notification."
                ),
            ),
            (
                "ru",
                (
                    "❌ Сессия записи истекла или была сброшена.\n\n"
                    "Пожалуйста, начните запись заново из уведомления о свободной "
                    "записи."
                ),
            ),
        ],
    )
    async def test_session_missing(self, db, lang, expected):
        add_user(db, lang)
        update = make_update(data=f"time_{TS}")

        state = await time_selected(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "✅ Selected time: 10:30 on 2025-01-15\n\n"
                    "Please enter your full name (as it appears on your documents):"
                ),
            ),
            (
                "ru",
                (
                    "✅ Выбранное время: 2025-01-15 в 10:30\n\n"
                    "Введите ваше полное имя (как в ваших документах):"
                ),
            ),
        ],
    )
    async def test_asks_for_name(self, db, lang, expected):
        add_user(db, lang)
        open_session()
        update = make_update(data=f"time_{TS}")

        state = await time_selected(update, make_context())

        assert state == ASKING_NAME
        edit = update.callback_query.edits[-1]
        assert edit.text == expected
        assert buttons(edit.reply_markup) == [(CANCEL_BOOKING[lang], "cancel_booking")]


@pytest.mark.asyncio
class TestNameReceived:
    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ Please enter your full name (first and last name).\n\n"
                    "Example: John Smith"
                ),
            ),
            (
                "ru",
                (
                    "❌ Пожалуйста, введите полное имя (имя и фамилию).\n\n"
                    "Пример: Ivan Petrov"
                ),
            ),
        ],
    )
    async def test_single_word(self, db, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS, state="ASKING_NAME")
        update = make_update(text="Ivan")

        state = await name_received(update, make_context())

        assert state == ASKING_NAME
        assert update.message.replies[-1].text == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "❌ Name is too short. Please enter your full name:"),
            ("ru", "❌ Имя слишком короткое. Пожалуйста, введите полное имя:"),
        ],
    )
    async def test_too_short(self, db, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS, state="ASKING_NAME")
        update = make_update(text="I P")

        state = await name_received(update, make_context())

        assert state == ASKING_NAME
        assert update.message.replies[-1].text == expected

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
    async def test_asks_for_email(self, db, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS, state="ASKING_NAME")
        update = make_update(text=NAME)

        state = await name_received(update, make_context())

        assert state == ASKING_EMAIL
        reply = update.message.replies[-1]
        assert reply.text == expected
        assert buttons(reply.reply_markup) == [(CANCEL_BOOKING[lang], "cancel_booking")]


@pytest.mark.asyncio
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
    async def test_invalid_email(self, db, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS, name=NAME, state="ASKING_EMAIL")
        update = make_update(text="not-an-email")

        state = await email_received(update, make_context())

        assert state == ASKING_EMAIL
        assert update.message.replies[-1].text == expected

    @pytest.mark.parametrize("lang", LANGS)
    async def test_session_expired(self, db, lang):
        add_user(db, lang)
        update = make_update(text=EMAIL)

        state = await email_received(update, make_context())

        assert state == ConversationHandler.END
        assert update.message.replies[-1].text == SESSION_EXPIRED[lang]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "📋 <b>Please confirm your booking:</b>\n\n"
                    "🕐 Time: 10:30 on Wednesday, January 15, 2025\n"
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
                    "🕐 Время: среда, 15 января 2025, 10:30\n"
                    "👤 Имя: Ivan Petrov\n"
                    "📧 Email: ivan@example.com\n\n"
                    "<b>Важно:</b> вам придёт письмо с подтверждением. "
                    "Обязательно перейдите по ссылке в этом письме, чтобы "
                    "окончательно подтвердить запись!"
                ),
            ),
        ],
    )
    async def test_confirmation_summary(self, db, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS, name=NAME, state="ASKING_EMAIL")
        update = make_update(text=EMAIL)

        state = await email_received(update, make_context())

        assert state == CONFIRMING
        reply = update.message.replies[-1]
        assert reply.text == expected
        assert reply.parse_mode == "HTML"
        assert buttons(reply.reply_markup) == [
            (CONFIRM[lang], "confirm_booking"),
            (CANCEL[lang], "cancel_booking"),
        ]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "🕐 Time: 09:05 on Wednesday, March 05, 2025\n"),
            ("ru", "🕐 Время: среда, 5 марта 2025, 09:05\n"),
        ],
    )
    async def test_single_digit_day(self, db, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS_SINGLE_DIGIT_DAY, name=NAME, state="ASKING_EMAIL")
        update = make_update(text=EMAIL)

        await email_received(update, make_context())

        assert expected in update.message.replies[-1].text


@pytest.mark.asyncio
class TestConfirmBooking:
    @pytest.mark.parametrize("lang", LANGS)
    async def test_cancel(self, db, lang):
        add_user(db, lang)
        open_session(timestamp=TS, name=NAME, email=EMAIL, state="CONFIRMING")
        update = make_update(data="cancel_booking")

        state = await confirm_booking(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == CANCELLED[lang]

    @pytest.mark.parametrize("lang", LANGS)
    async def test_session_expired(self, db, lang):
        add_user(db, lang)
        update = make_update(data="confirm_booking")

        state = await confirm_booking(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == SESSION_EXPIRED[lang]

    @pytest.mark.parametrize(
        ("lang", "processing", "expected"),
        [
            (
                "en",
                "⏳ Processing your booking...\nThis may take a few seconds.",
                (
                    "🎉 <b>Booking Successful!</b> 🎉\n\n"
                    "📋 Booking ID: P-42\n"
                    "🕐 Time: 10:30 on Wednesday, January 15, 2025\n"
                    "👤 Name: Ivan Petrov\n"
                    "📧 Email: ivan@example.com\n\n"
                    "<b>⚠️ IMPORTANT - Next Steps:</b>\n\n"
                    "1. Check your email inbox at <b>ivan@example.com</b>\n"
                    "2. Look for a confirmation email from Munich Ausländerbehörde\n"
                    "3. <b>Click the confirmation link</b> in that email\n"
                    "4. Your appointment will only be finalized after email "
                    "confirmation\n\n"
                    "If you don't see the email within 5 minutes, check your spam "
                    "folder."
                ),
            ),
            (
                "ru",
                "⏳ Оформляю запись...\nЭто может занять несколько секунд.",
                (
                    "🎉 <b>Запись оформлена!</b> 🎉\n\n"
                    "📋 Номер записи: P-42\n"
                    "🕐 Время: среда, 15 января 2025, 10:30\n"
                    "👤 Имя: Ivan Petrov\n"
                    "📧 Email: ivan@example.com\n\n"
                    "<b>⚠️ ВАЖНО — что делать дальше:</b>\n\n"
                    "1. Проверьте почтовый ящик <b>ivan@example.com</b>\n"
                    "2. Найдите письмо с подтверждением от Ausländerbehörde München\n"
                    "3. <b>Перейдите по ссылке для подтверждения</b> в этом письме\n"
                    "4. Запись будет окончательно оформлена только после "
                    "подтверждения по email\n\n"
                    "Если письмо не пришло в течение 5 минут, проверьте папку "
                    "«Спам»."
                ),
            ),
        ],
    )
    async def test_success(self, db, monkeypatch, lang, processing, expected):
        add_user(db, lang)
        open_session(timestamp=TS, name=NAME, email=EMAIL, state="CONFIRMING")
        monkeypatch.setattr(
            booking, "book_appointment_complete", lambda **kw: {"processId": "P-42"}
        )
        update = make_update(data="confirm_booking")

        state = await confirm_booking(update, make_context())

        assert state == ConversationHandler.END
        edits = update.callback_query.edits
        assert [e.text for e in edits] == [processing, expected]
        assert edits[-1].parse_mode == "HTML"
        assert buttons(edits[-1].reply_markup) == [(MAIN_MENU[lang], "main_menu")]
        assert get_booking_session(USER_ID) is None

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ <b>Booking Failed</b>\n\n"
                    "The appointment could not be booked. Possible reasons:\n"
                    "• The slot was just taken by someone else\n"
                    "• Network error occurred\n"
                    "• Captcha token expired\n\n"
                    "Please try booking another available slot."
                ),
            ),
            (
                "ru",
                (
                    "❌ <b>Запись не удалась</b>\n\n"
                    "Не удалось оформить запись. Возможные причины:\n"
                    "• это время только что занял кто-то другой\n"
                    "• произошла ошибка сети\n"
                    "• истёк срок действия капчи\n\n"
                    "Пожалуйста, попробуйте выбрать другое свободное время."
                ),
            ),
        ],
    )
    async def test_failure(self, db, monkeypatch, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS, name=NAME, email=EMAIL, state="CONFIRMING")
        monkeypatch.setattr(booking, "book_appointment_complete", lambda **kw: None)
        update = make_update(data="confirm_booking")

        await confirm_booking(update, make_context())

        edit = update.callback_query.edits[-1]
        assert edit.text == expected
        assert edit.parse_mode == "HTML"
        assert buttons(edit.reply_markup) == [(MAIN_MENU[lang], "main_menu")]

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            (
                "en",
                (
                    "❌ An error occurred while booking:\nboom\n\n"
                    "Please try again or contact support."
                ),
            ),
            (
                "ru",
                (
                    "❌ При оформлении записи произошла ошибка:\nboom\n\n"
                    "Пожалуйста, попробуйте снова или обратитесь в поддержку."
                ),
            ),
        ],
    )
    async def test_error(self, db, monkeypatch, caplog, lang, expected):
        add_user(db, lang)
        open_session(timestamp=TS, name=NAME, email=EMAIL, state="CONFIRMING")

        def fail(**kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(booking, "book_appointment_complete", fail)
        update = make_update(data="confirm_booking")

        await confirm_booking(update, make_context())

        edit = update.callback_query.edits[-1]
        assert edit.text == expected
        assert buttons(edit.reply_markup) == [(MAIN_MENU[lang], "main_menu")]
        assert [r.getMessage() for r in caplog.records] == ["Booking error: boom"]


@pytest.mark.asyncio
class TestCancellation:
    @pytest.mark.parametrize("lang", LANGS)
    async def test_cancel_button(self, db, lang):
        add_user(db, lang)
        open_session(timestamp=TS, state="ASKING_NAME")
        update = make_update(data="cancel_booking")

        state = await cancel_booking_button(update, make_context())

        assert state == ConversationHandler.END
        assert update.callback_query.edits[-1].text == CANCELLED[lang]

    @pytest.mark.parametrize("lang", LANGS)
    async def test_command_fallback(self, db, lang):
        add_user(db, lang)
        open_session(timestamp=TS, state="ASKING_NAME")
        update = make_update(text="/menu")

        state = await cancel_booking_conversation(update, make_context())

        assert state == ConversationHandler.END
        assert update.message.replies[-1].text == CANCELLED[lang]
