# ABOUTME: Tests for the one-time new-menu announcement at startup (S31, section 9.3).
# ABOUTME: Real in-memory DB, recording FakeBot.

import pytest
from sqlmodel import Session
from telegram import ReplyKeyboardMarkup
from telegram.error import Forbidden, NetworkError

from src.i18n import t
from src.repositories import UserRepository, WatchRepository
from src.services.announcement import announce_new_ui
from src.ui.commands_menu import bot_commands
from src.watches.when import PRESETS
from tests.fakes import FakeBot

pytestmark = pytest.mark.asyncio

WITH_WATCH_EN = 1
WITHOUT_WATCH_RU = 2
NO_LANGUAGE = 3
ALREADY_CURRENT = 4
LEVEL_ONE_WITH_WATCH = 5
WITH_WATCH_RU = 6


def add_user(db, user_id, language, ui_version=0, watches=0):
    with Session(db) as session:
        users = UserRepository(session)
        users.create_user(user_id, language=language)
        users.set_ui_version(user_id, ui_version)
        for service_id in (1063475, 1063441)[:watches]:
            WatchRepository(session).create_or_update(
                user_id, service_id, None, PRESETS["asap"]
            )


def ui_version(db, user_id):
    with Session(db) as session:
        return UserRepository(session).get_user(user_id).ui_version


@pytest.fixture
def users(db):
    add_user(db, WITH_WATCH_EN, "en", watches=2)
    add_user(db, WITHOUT_WATCH_RU, "ru")
    add_user(db, NO_LANGUAGE, "", watches=1)
    add_user(db, ALREADY_CURRENT, "en", ui_version=2, watches=1)
    add_user(db, LEVEL_ONE_WITH_WATCH, "en", ui_version=1, watches=1)
    add_user(db, WITH_WATCH_RU, "ru", watches=1)


async def test_levels_commands_and_messages(db, users):
    bot = FakeBot()

    assert await announce_new_ui(bot) == 2

    by_chat = {c.chat_id: c for c in bot.sent}
    assert set(by_chat) == {WITH_WATCH_EN, WITH_WATCH_RU}
    for chat_id, lang in ((WITH_WATCH_EN, "en"), (WITH_WATCH_RU, "ru")):
        sent = by_chat[chat_id]
        assert sent.text == t(
            "start.announce", lang, watches=t("keyboard.watches", lang)
        )
        assert sent.parse_mode == "HTML"
        assert isinstance(sent.reply_markup, ReplyKeyboardMarkup)
        assert sent.reply_markup.keyboard[0][1].text == t("keyboard.watches", lang)

    commands = {c.scope.chat_id: c.commands for c in bot.calls_of("set_my_commands")}
    assert commands == {
        WITH_WATCH_EN: bot_commands("en"),
        WITHOUT_WATCH_RU: bot_commands("ru"),
        WITH_WATCH_RU: bot_commands("ru"),
    }
    assert ui_version(db, WITH_WATCH_EN) == 2
    assert ui_version(db, WITH_WATCH_RU) == 2
    assert ui_version(db, WITHOUT_WATCH_RU) == 1
    assert ui_version(db, NO_LANGUAGE) == 0
    assert ui_version(db, ALREADY_CURRENT) == 2
    assert ui_version(db, LEVEL_ONE_WITH_WATCH) == 1


async def test_idempotent(db, users):
    await announce_new_ui(FakeBot())
    bot = FakeBot()
    assert await announce_new_ui(bot) == 0
    assert bot.calls == []


async def test_blocked_user_is_paused_and_not_retried(db):
    add_user(db, WITH_WATCH_EN, "en", watches=2)
    bot = FakeBot()
    bot.fail_next("send_message", Forbidden("Forbidden: bot was blocked by the user"))

    assert await announce_new_ui(bot) == 0

    assert ui_version(db, WITH_WATCH_EN) == 2
    with Session(db) as session:
        recs = WatchRepository(session).list_for_user(WITH_WATCH_EN, None)
    assert [(r.status, r.pause_reason) for r in recs] == [("paused", "blocked")] * 2


async def test_transient_failure_is_retried_next_start(db, caplog):
    add_user(db, WITH_WATCH_EN, "en", watches=1)
    bot = FakeBot()
    bot.fail_next("send_message", NetworkError("connection reset"))

    assert await announce_new_ui(bot) == 0
    assert ui_version(db, WITH_WATCH_EN) == 0
    assert any("connection reset" in r.getMessage() for r in caplog.records)

    bot = FakeBot()
    assert await announce_new_ui(bot) == 1
    assert ui_version(db, WITH_WATCH_EN) == 2
