# ABOUTME: Tests for handlers that run on every update: interaction tracker, presence, error handler.
# ABOUTME: Real DB (in-memory), real Update objects bound to the recording FakeBot.

import logging
from datetime import timedelta

import pytest
from sqlmodel import Session
from telegram import ReplyKeyboardMarkup

from src.handlers import errors as errors_module
from src.handlers.errors import on_error
from src.handlers.interaction_tracker import record_interaction
from src.handlers.presence import on_presence
from src.i18n import t
from src.repositories import PendingRetireRepository, UserRepository, WatchRepository
from src.ui.commands_menu import bot_commands
from src.watches.when import PRESETS
from tests.fakes import FakeBot, FakeContext, make_callback_update, make_text_update

pytestmark = pytest.mark.asyncio

USER = 4242


def add_user(db, language="en", ui_version=0, user_id=USER):
    with Session(db) as session:
        users = UserRepository(session)
        users.create_user(user_id, language=language)
        users.set_ui_version(user_id, ui_version)


def user(db):
    with Session(db) as session:
        return UserRepository(session).get_user(USER)


class TestInteractionTracker:
    async def test_marks_live_alert_and_touches_queue(self, db, clock):
        add_user(db)
        with Session(db) as session:
            watches = WatchRepository(session)
            rec, _ = watches.create_or_update(USER, 1, None, PRESETS["asap"])
            watches.set_live_alert(
                rec.id, USER, 70, "slots", frozenset(), frozenset(), "h"
            )
            PendingRetireRepository(session).add(USER, USER, 71, "old", clock.now)
        bot = FakeBot()

        await record_interaction(
            make_callback_update("w1:stop:1", message_id=70, bot=bot), FakeContext(bot)
        )
        await record_interaction(
            make_callback_update("b1:x", message_id=71, bot=bot), FakeContext(bot)
        )

        with Session(db) as session:
            assert WatchRepository(session).get(rec.id).interacted_at == clock.now
            retires = PendingRetireRepository(session)
            assert retires.due(clock.now + timedelta(minutes=9)) == []
            assert len(retires.due(clock.now + timedelta(minutes=10))) == 1
        assert bot.calls == []

    async def test_other_message_and_text_untouched(self, db, clock):
        add_user(db)
        with Session(db) as session:
            rec, _ = WatchRepository(session).create_or_update(
                USER, 1, None, PRESETS["asap"]
            )
        await record_interaction(
            make_callback_update("f1:home", message_id=5), FakeContext()
        )
        await record_interaction(make_text_update("hello"), FakeContext())
        with Session(db) as session:
            assert WatchRepository(session).get(rec.id).interacted_at is None


class TestPresence:
    async def test_keyboard_line_once_for_old_ui(self, db):
        add_user(db, "ru", ui_version=0)
        bot = FakeBot()
        context = FakeContext(bot)

        await on_presence(make_callback_update("myservices", bot=bot), context)

        [sent] = bot.sent
        assert sent.text == t("keyboard.upgrade", "ru")
        assert isinstance(sent.reply_markup, ReplyKeyboardMarkup)
        [commands] = bot.calls_of("set_my_commands")
        assert commands.commands == bot_commands("ru")
        assert commands.scope.chat_id == USER
        assert user(db).ui_version == 2

        await on_presence(make_text_update("/find", bot=bot), context)
        assert len(bot.sent) == 1

    async def test_level_one_gets_keyboard_without_commands(self, db):
        add_user(db, "en", ui_version=1)
        bot = FakeBot()
        await on_presence(make_text_update("passport", bot=bot), FakeContext(bot))
        assert [s.text for s in bot.sent] == [t("keyboard.upgrade", "en")]
        assert bot.calls_of("set_my_commands") == []
        assert user(db).ui_version == 2

    @pytest.mark.parametrize(
        "kwargs", [{"text": "/start"}, {"text": "/start@Bot x"}, {"data": "lang:ru"}]
    )
    async def test_not_on_start_or_language_choice(self, db, kwargs):
        add_user(db, "en", ui_version=0)
        bot = FakeBot()
        update = (
            make_text_update(kwargs["text"], bot=bot)
            if "text" in kwargs
            else make_callback_update(kwargs["data"], bot=bot)
        )
        await on_presence(update, FakeContext(bot))
        assert bot.calls == []
        assert user(db).ui_version == 0

    async def test_current_ui_sends_nothing(self, db):
        add_user(db, "en", ui_version=2)
        bot = FakeBot()
        await on_presence(make_text_update("/watches", bot=bot), FakeContext(bot))
        assert bot.calls == []

    @pytest.mark.parametrize("language", ["", None])
    async def test_unregistered_or_no_language_skipped(self, db, language):
        if language is not None:
            add_user(db, language)
        bot = FakeBot()
        await on_presence(make_text_update("/find", bot=bot), FakeContext(bot))
        assert bot.calls == []

    async def test_group_chat_skipped(self, db):
        add_user(db, "en", ui_version=0)
        bot = FakeBot()
        await on_presence(
            make_text_update("hi", chat_type="group", chat_id=-100, bot=bot),
            FakeContext(bot),
        )
        assert bot.calls == []

    async def test_blocked_pauses_resumed_with_note(self, db):
        add_user(db, "ru", ui_version=2)
        with Session(db) as session:
            watches = WatchRepository(session)
            watches.create_or_update(USER, 1, None, PRESETS["asap"])
            watches.create_or_update(USER, 2, None, PRESETS["asap"])
            watches.pause_all_for_user(USER)
        bot = FakeBot()

        await on_presence(make_text_update("hi", bot=bot), FakeContext(bot))

        assert [s.text for s in bot.sent] == [t("watch.resumed", "ru", count=2)]
        with Session(db) as session:
            assert WatchRepository(session).count_open(USER) == 2
            assert all(
                r.status == "active" for r in WatchRepository(session).list_active()
            )
        await on_presence(make_text_update("hi", bot=bot), FakeContext(bot))
        assert len(bot.sent) == 1


class TestErrorHandler:
    async def test_logs_and_tracks(self, events, caplog):
        events.patch(errors_module)
        context = FakeContext()
        context.error = ValueError("boom")

        with caplog.at_level(logging.ERROR, logger="src.handlers.errors"):
            await on_error(make_text_update("x"), context)

        [record] = [r for r in caplog.records if r.name == "src.handlers.errors"]
        assert record.exc_info[1] is context.error
        assert events.calls == [
            ("handler_error", {"user_id": None, "error_type": "ValueError"})
        ]

    async def test_without_update(self, events, caplog):
        events.patch(errors_module)
        context = FakeContext()
        context.error = RuntimeError("background")
        with caplog.at_level(logging.ERROR, logger="src.handlers.errors"):
            await on_error(None, context)
        assert events.calls[0][1]["error_type"] == "RuntimeError"
