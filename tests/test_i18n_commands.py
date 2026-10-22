# ABOUTME: Tests that /help and the /stats refusal reply in the user's language, and the command lists.
# ABOUTME: Real in-memory DB; Telegram is the recording FakeBot from tests/fakes.py.

import logging

import pytest
from sqlmodel import Session

from src.commands.help import help_command
from src.commands.stats import stats_command
from src.config import get_config
from src.handlers import text_input
from src.i18n import t
from src.repositories import UserRepository
from src.ui.commands_menu import BOT_COMMANDS, bot_commands
from tests.fakes import FakeBot, FakeContext, make_text_update

USER_ID = 5151


def add_user(db, language):
    with Session(db) as session:
        UserRepository(session).create_user(
            user_id=USER_ID, username="tester", language=language
        )


def buttons(markup) -> list[list[tuple[str, str]]]:
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


@pytest.fixture(autouse=True)
def pending_input(monkeypatch):
    calls = []
    monkeypatch.setattr(
        text_input, "clear_pending_input", lambda context: calls.append(context)
    )
    return calls


async def run(handler):
    bot = FakeBot()
    context = FakeContext(bot)
    await handler(make_text_update("/x", user_id=USER_ID, bot=bot), context)
    return bot, context


@pytest.mark.asyncio
class TestHelp:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_text_and_buttons(self, db, pending_input, lang):
        add_user(db, lang)
        bot, context = await run(help_command)

        [sent] = bot.sent
        assert sent.text == t("help.text", lang, find=t("keyboard.find", lang))
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [
            [
                (t("keyboard.find", lang), "f1:home"),
                (t("keyboard.watches", lang), "w1:list"),
            ]
        ]
        assert pending_input == [context]
        with Session(db) as session:
            assert UserRepository(session).get_nav_message_id(USER_ID) == (
                sent.message_id
            )

    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_lists_user_commands_and_no_retired_ones(self, db, lang):
        add_user(db, lang)
        bot, _ = await run(help_command)
        text = bot.sent[0].text
        for command in ("find", "watches", "settings", "language", "stop", "help"):
            assert f"/{command} " in text
        for retired in ("/menu", "/subscribe", "/myservices", "/setdates", "/status"):
            assert retired not in text

    async def test_russian_has_no_english_words(self, db):
        add_user(db, "ru")
        bot, _ = await run(help_command)
        text = bot.sent[0].text
        assert "How it works" not in text
        assert "Commands" not in text

    async def test_unregistered_user_gets_english_help(self, db):
        bot, _ = await run(help_command)
        assert bot.sent[0].text == t("help.text", "en", find=t("keyboard.find", "en"))


class TestCommandDescriptions:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_seven_commands_described(self, lang):
        commands = bot_commands(lang)
        assert [c.command for c in commands] == list(BOT_COMMANDS)
        assert len(commands) == 7
        for command in commands:
            assert command.description == t(f"commands.{command.command}", lang)
            assert 1 <= len(command.description) <= 256

    @pytest.mark.parametrize("lang", ["en", "ru"])
    @pytest.mark.parametrize(
        "retired", ["menu", "subscribe", "myservices", "setdates", "status"]
    )
    def test_retired_commands_have_no_description(self, lang, retired):
        with pytest.raises(KeyError):
            t(f"commands.{retired}", lang)


@pytest.mark.asyncio
class TestStats:
    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("en", "⛔️ This command is only available to the bot administrator."),
            ("ru", "⛔️ Эта команда доступна только администратору бота."),
        ],
    )
    async def test_non_admin_is_refused_in_own_language(
        self, db, monkeypatch, caplog, lang, text
    ):
        monkeypatch.setattr(get_config(), "admin_telegram_id", USER_ID + 1)
        add_user(db, lang)
        bot = FakeBot()
        update = make_text_update("/stats", user_id=USER_ID, bot=bot)
        with caplog.at_level(logging.WARNING, logger="src.commands.stats"):
            await stats_command(update, FakeContext(bot))
        assert [s.text for s in bot.sent] == [text]
        assert [r.getMessage() for r in caplog.records] == [
            f"User {USER_ID} attempted to access /stats command"
        ]
