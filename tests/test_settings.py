# ABOUTME: Tests for the Settings screen (S20): language, saved booking details, entry to data deletion.
# ABOUTME: Real in-memory DB; Telegram is the recording FakeBot from tests/fakes.py.

import pytest
from sqlmodel import Session

from src.commands.settings import settings_callback, settings_command
from src.handlers import text_input
from src.i18n import t
from src.repositories import UserRepository
from tests.fakes import FakeBot, FakeContext, make_callback_update, make_text_update

pytestmark = pytest.mark.asyncio

USER = 4242
SETTINGS_MSG = 60


def add_user(db, language="en", contact=None):
    with Session(db) as session:
        users = UserRepository(session)
        users.create_user(USER, language=language)
        if contact is not None:
            users.set_booking_contact(USER, *contact)


def contact(db):
    with Session(db) as session:
        return UserRepository(session).get_booking_contact(USER)


def nav_pointer(db):
    with Session(db) as session:
        return UserRepository(session).get_nav_message_id(USER)


def buttons(markup) -> list[list[tuple[str, str]]]:
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


def settings_text(lang, contact_text=None):
    return t(
        "settings.text",
        lang,
        language=t(f"language.btn_{lang}", lang),
        contact=contact_text or t("settings.contact_none", lang),
    )


@pytest.fixture(autouse=True)
def pending_input(monkeypatch):
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


def press(data, bot, message_id=SETTINGS_MSG):
    return make_callback_update(data, message_id=message_id, bot=bot)


class TestSettingsScreen:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_command_without_saved_contact(
        self, db, bot, ctx, pending_input, lang
    ):
        add_user(db, lang)

        await settings_command(make_text_update("/settings", bot=bot), ctx)

        [sent] = bot.sent
        assert sent.text == settings_text(lang)
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [
            [(t("language.btn_menu", lang), "language")],
            [(t("settings.btn_delete", lang), "s1:del")],
        ]
        assert nav_pointer(db) == sent.message_id
        assert pending_input == [ctx]

    async def test_saved_contact_is_shown_escaped_with_forget(self, db, bot, ctx):
        add_user(db, "en", contact=("Ivan <Petrov>", "ivan&co@example.com"))

        await settings_command(make_text_update("/settings", bot=bot), ctx)

        [sent] = bot.sent
        assert sent.text == settings_text(
            "en", "Ivan &lt;Petrov&gt;, ivan&amp;co@example.com"
        )
        assert buttons(sent.reply_markup) == [
            [(t("language.btn_menu", "en"), "language")],
            [(t("settings.btn_forget", "en"), "s1:forget")],
            [(t("settings.btn_delete", "en"), "s1:del")],
        ]

    async def test_unregistered(self, db, bot, ctx):
        await settings_command(make_text_update("/settings", bot=bot), ctx)
        assert [s.text for s in bot.sent] == [t("start.not_registered", "en")]

    async def test_home_button_edits_in_place(self, db, bot, ctx, pending_input):
        add_user(db, "ru")

        await settings_callback(press("s1:home", bot), ctx)

        [edit] = bot.edits
        assert edit.message_id == SETTINGS_MSG
        assert edit.text == settings_text("ru")
        assert nav_pointer(db) == SETTINGS_MSG
        assert pending_input == [ctx]


class TestForgetContact:
    async def test_forget_clears_and_rerenders(self, db, bot, ctx):
        add_user(db, "en", contact=("Ivan", "ivan@example.com"))

        await settings_callback(press("s1:forget", bot), ctx)

        assert contact(db) is None
        [answer] = bot.calls_of("answer_callback_query")
        assert answer.text == t("settings.forgotten", "en")
        [edit] = bot.edits
        assert edit.text == settings_text("en")
        assert (t("settings.btn_forget", "en"), "s1:forget") not in [
            b for row in buttons(edit.reply_markup) for b in row
        ]


class TestDeleteEntry:
    async def test_delete_asks_in_place_and_no_goes_back(self, db, bot, ctx):
        add_user(db, "ru")

        await settings_callback(press("s1:del", bot), ctx)

        [confirm] = bot.edits
        assert confirm.message_id == SETTINGS_MSG
        assert confirm.text == t("stop.confirm", "ru")
        assert buttons(confirm.reply_markup) == [
            [
                (t("stop.btn_yes", "ru"), "s1:dely"),
                (t("stop.btn_no", "ru"), "s1:deln"),
            ]
        ]

        await settings_callback(press("s1:deln", bot), ctx)

        _, back = bot.edits
        assert back.message_id == SETTINGS_MSG
        assert back.text == settings_text("ru")
        with Session(db) as session:
            assert UserRepository(session).get_user(USER) is not None
