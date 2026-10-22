# ABOUTME: Tests for navigation helpers: reply keyboard, command lists, nav screens, background tasks.
# ABOUTME: Telegram is the recording FakeBot; the nav pointer lives in an in-memory SQLite DB.

import asyncio

import pytest
from sqlmodel import Session
from telegram import ReplyKeyboardMarkup
from telegram.error import BadRequest, TelegramError

from src.i18n import SUPPORTED_LANGUAGES, t
from src.repositories import UserRepository
from src.ui import commands_menu, keyboard
from src.ui.background import run_for_user, user_lock
from src.ui.commands_menu import (
    BOT_COMMANDS,
    bot_commands,
    set_chat_commands,
    set_default_commands,
)
from src.ui.keyboard import MENU_FILTER, MenuAction, main_keyboard, menu_action
from src.ui.screens import forget_nav_message, retire_nav_message, show_screen
from tests.fakes import FakeBot, FakeContext, make_callback_update, make_text_update

USER = 4242


class TestReplyKeyboard:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_layout(self, lang):
        markup = main_keyboard(lang)
        assert isinstance(markup, ReplyKeyboardMarkup)
        assert [[b.text for b in row] for row in markup.keyboard] == [
            [t("keyboard.find", lang), t("keyboard.watches", lang)],
            [t("keyboard.settings", lang), t("keyboard.help", lang)],
        ]
        assert markup.resize_keyboard is True
        assert markup.is_persistent is True

    @pytest.mark.parametrize("lang", ["en", "ru"])
    @pytest.mark.parametrize("action", list(MenuAction))
    def test_both_languages_match(self, lang, action):
        label = t(f"keyboard.{action.value}", lang)
        assert menu_action(label) is action
        assert menu_action(f"  {label} ") is action

    def test_unknown_text(self):
        assert menu_action("Find") is None
        assert menu_action("") is None
        assert menu_action(None) is None

    def test_labels_unique_across_actions_and_languages(self):
        labels = [
            t(f"keyboard.{a.value}", lang)
            for lang in SUPPORTED_LANGUAGES
            for a in MenuAction
        ]
        assert len(set(labels)) == len(labels)

    def test_filter_matches_labels_only(self):
        assert MENU_FILTER.check_update(make_text_update(t("keyboard.watches", "ru")))
        assert not MENU_FILTER.check_update(make_text_update("passport"))

    def test_module_constant(self):
        assert keyboard.MENU_FILTER is MENU_FILTER


class TestCommandsMenu:
    def test_commands(self):
        assert BOT_COMMANDS == (
            "start",
            "find",
            "watches",
            "settings",
            "help",
            "language",
            "stop",
        )

    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_descriptions(self, lang):
        commands = bot_commands(lang)
        assert [c.command for c in commands] == list(BOT_COMMANDS)
        for command in commands:
            assert command.description == t(f"commands.{command.command}", lang)
            assert 1 <= len(command.description) <= 256

    @pytest.mark.asyncio
    async def test_default_commands(self):
        bot = FakeBot()
        await set_default_commands(bot)
        by_code = {c.language_code: c.commands for c in bot.calls_of("set_my_commands")}
        assert by_code == {None: bot_commands("en"), "ru": bot_commands("ru")}

    @pytest.mark.asyncio
    async def test_chat_commands(self):
        bot = FakeBot()
        assert await set_chat_commands(bot, 77, "ru") is True
        [call] = bot.calls_of("set_my_commands")
        assert call.scope.chat_id == 77
        assert call.commands == bot_commands("ru")

    @pytest.mark.asyncio
    async def test_chat_commands_failure_is_logged(self, caplog):
        bot = FakeBot()
        bot.fail_next("set_my_commands", TelegramError("network down"))
        assert await set_chat_commands(bot, 77, "en") is False
        assert any("network down" in r.getMessage() for r in caplog.records)
        assert commands_menu.BOT_COMMANDS is BOT_COMMANDS


@pytest.fixture
def user(db):
    with Session(db) as session:
        UserRepository(session).create_user(USER, language="en")
    return USER


def pointer(db):
    with Session(db) as session:
        return UserRepository(session).get_nav_message_id(USER)


def set_pointer(db, message_id):
    with Session(db) as session:
        UserRepository(session).set_nav_message_id(USER, message_id)


@pytest.mark.asyncio
class TestShowScreen:
    async def test_message_update_sends_new_and_strips_previous(self, db, user):
        bot = FakeBot()
        set_pointer(db, 10)
        context = FakeContext(bot)

        message = await show_screen(
            make_text_update("/watches", bot=bot), context, "<b>A</b>", None
        )

        assert message.message_id == bot.sent[0].message_id
        assert bot.sent[0].parse_mode == "HTML"
        [strip] = bot.calls_of("edit_message_reply_markup")
        assert strip.message_id == 10
        assert pointer(db) == message.message_id

    async def test_callback_edits_pressed_message(self, db, user):
        bot = FakeBot()
        set_pointer(db, 20)
        update = make_callback_update("w1:list", message_id=20, bot=bot)

        await show_screen(update, FakeContext(bot), "text", None)

        [edit] = bot.edits
        assert (edit.message_id, edit.text) == (20, "text")
        assert bot.calls_of("edit_message_reply_markup") == []
        assert bot.sent == []
        assert pointer(db) == 20

    async def test_callback_on_other_message_strips_stale_pointer(self, db, user):
        bot = FakeBot()
        set_pointer(db, 20)
        update = make_callback_update("w1:list", message_id=30, bot=bot)

        await show_screen(update, FakeContext(bot), "text", None)

        assert [c.message_id for c in bot.calls_of("edit_message_reply_markup")] == [20]
        assert bot.edits[0].message_id == 30
        assert pointer(db) == 30

    async def test_not_modified_is_ignored(self, db, user):
        bot = FakeBot()
        bot.fail_next("edit_message_text", BadRequest("Message is not modified"))
        update = make_callback_update("w1:list", message_id=30, bot=bot)

        assert await show_screen(update, FakeContext(bot), "text", None) is not None
        assert bot.sent == []
        assert pointer(db) == 30

    async def test_uneditable_pressed_message_falls_back_to_new_message(self, db, user):
        bot = FakeBot()
        bot.fail_next("edit_message_text", BadRequest("Message can't be edited"))
        update = make_callback_update("w1:list", message_id=30, bot=bot)

        message = await show_screen(update, FakeContext(bot), "text", None)

        assert message.message_id == bot.sent[0].message_id
        assert pointer(db) == message.message_id

    async def test_pointer_survives_user_data_clear(self, db, user):
        bot = FakeBot()
        context = FakeContext(bot)
        first = await show_screen(
            make_text_update("/watches", bot=bot), context, "a", None
        )
        context.user_data.clear()
        await show_screen(make_text_update("/settings", bot=bot), context, "b", None)
        assert (
            bot.calls_of("edit_message_reply_markup")[0].message_id == first.message_id
        )

    async def test_forget_and_retire(self, db, user):
        set_pointer(db, 20)
        forget_nav_message(USER, 21)
        assert pointer(db) == 20
        forget_nav_message(USER, 20)
        assert pointer(db) is None

        set_pointer(db, 22)
        forget_nav_message(USER)
        assert pointer(db) is None

        bot = FakeBot()
        set_pointer(db, 23)
        await retire_nav_message(bot, USER)
        assert bot.calls_of("edit_message_reply_markup")[0].message_id == 23
        assert pointer(db) is None
        await retire_nav_message(bot, USER)
        assert len(bot.calls_of("edit_message_reply_markup")) == 1


@pytest.mark.asyncio
class TestBackground:
    async def test_runs_in_background_in_order_per_user(self):
        context = FakeContext()
        gate = asyncio.Event()
        order = []

        async def slow():
            await gate.wait()
            order.append("slow")

        async def fast():
            order.append("fast")

        update = make_text_update("x")
        run_for_user(context, update, USER, slow())
        run_for_user(context, update, USER, fast())
        await asyncio.sleep(0)
        assert order == []
        gate.set()
        await context.drain()
        assert order == ["slow", "fast"]

    async def test_other_users_do_not_wait(self):
        context = FakeContext()
        gate = asyncio.Event()
        order = []

        async def blocked():
            await gate.wait()
            order.append("a")

        async def other():
            order.append("b")

        run_for_user(context, None, 1, blocked())
        run_for_user(context, None, 2, other())
        await asyncio.sleep(0.01)
        assert order == ["b"]
        gate.set()
        await context.drain()
        assert user_lock(1) is user_lock(1)
