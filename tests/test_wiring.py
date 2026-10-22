# ABOUTME: Tests for handler registration in telegram_bot.py: groups, routing, private-only, startup order.
# ABOUTME: Routing is checked with PTB's own check_update against real Update objects.

import pytest
from telegram import Update
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
)

import telegram_bot
from src.commands.booking import booking_orphan_callback
from src.commands.find import find_callback, find_command
from src.commands.help import help_command
from src.commands.language import (
    language_choice_callback,
    language_command,
    language_gate,
    language_menu_callback,
)
from src.commands.settings import settings_callback, settings_command
from src.commands.start import start_command
from src.commands.stats import stats_command
from src.commands.stop import stop_command
from src.commands.watches import watches_callback, watches_command
from src.handlers.errors import on_error
from src.handlers.interaction_tracker import record_interaction
from src.handlers.legacy_callbacks import legacy_callback
from src.handlers.menu_keyboard import menu_text
from src.handlers.presence import on_presence
from src.handlers.text_input import on_text
from src.i18n import t
from tests.fakes import make_callback_update, make_text_update


@pytest.fixture(scope="module")
def application():
    app = telegram_bot.build_application("1:test")
    telegram_bot.register_handlers(app)
    return app


def first_match(application, group, update):
    for handler in application.handlers.get(group, []):
        if handler.check_update(update):
            return handler
    return None


def test_builder_uses_rate_limiter(application):
    assert isinstance(application.bot.rate_limiter, AIORateLimiter)


def test_groups(application):
    assert sorted(application.handlers) == [-3, -2, -1, 0, 1]
    [presence] = application.handlers[-3]
    assert isinstance(presence, TypeHandler) and presence.callback is on_presence
    [tracker] = application.handlers[-2]
    assert (
        isinstance(tracker, CallbackQueryHandler)
        and tracker.callback is record_interaction
    )
    [gate] = application.handlers[-1]
    assert isinstance(gate, TypeHandler) and gate.callback is language_gate
    [booking] = application.handlers[0]
    assert isinstance(booking, ConversationHandler)


def test_error_handler(application):
    assert on_error in application.error_handlers


@pytest.mark.parametrize(
    ("command", "callback"),
    [
        ("/start", start_command),
        ("/find", find_command),
        ("/watches", watches_command),
        ("/settings", settings_command),
        ("/help", help_command),
        ("/language", language_command),
        ("/stop", stop_command),
        ("/stats", stats_command),
        ("/menu", find_command),
        ("/subscribe", find_command),
        ("/myservices", watches_command),
        ("/status", watches_command),
        ("/setdates", watches_command),
    ],
)
def test_commands(application, command, callback):
    handler = first_match(application, 1, make_text_update(command))
    assert isinstance(handler, CommandHandler)
    assert handler.callback is callback


@pytest.mark.parametrize(
    ("data", "callback"),
    [
        ("lang:ru", language_choice_callback),
        ("language", language_menu_callback),
        ("f1:home", find_callback),
        ("f1:when:1063475:0:asap", find_callback),
        ("w1:list", watches_callback),
        ("s1:del", settings_callback),
        ("b1:me", booking_orphan_callback),
        ("b1:17:20261029", booking_orphan_callback),
        ("time_1796292600", booking_orphan_callback),
        ("confirm_booking", booking_orphan_callback),
        ("cancel_booking", booking_orphan_callback),
        ("main_menu", legacy_callback),
        ("unsub:1", legacy_callback),
        ("anything", legacy_callback),
    ],
)
def test_callbacks(application, data, callback):
    handler = first_match(application, 1, make_callback_update(data))
    assert isinstance(handler, CallbackQueryHandler)
    assert handler.callback is callback


@pytest.mark.parametrize("lang", ["en", "ru"])
@pytest.mark.parametrize(
    "key", ["keyboard.find", "keyboard.watches", "keyboard.settings", "keyboard.help"]
)
def test_menu_labels_route_to_menu(application, lang, key):
    handler = first_match(application, 1, make_text_update(t(key, lang)))
    assert isinstance(handler, MessageHandler) and handler.callback is menu_text


def test_plain_text_routes_to_text_input(application):
    handler = first_match(application, 1, make_text_update("passport"))
    assert isinstance(handler, MessageHandler) and handler.callback is on_text


@pytest.mark.parametrize("text", ["passport", "/find", t("keyboard.find", "en")])
def test_group_chat_messages_are_ignored(application, text):
    update = make_text_update(text, chat_type="group", chat_id=-100)
    assert first_match(application, 1, update) is None


def test_tracker_sees_every_callback(application):
    [tracker] = application.handlers[-2]
    for data in ("f1:home", "b1:me", "main_menu"):
        assert tracker.check_update(make_callback_update(data))


@pytest.mark.asyncio
class TestStartup:
    async def test_post_init_order(self, monkeypatch):
        calls = []

        async def set_default_commands(bot):
            calls.append("commands")

        async def end_all_booking_sessions(bot):
            calls.append("bookings")
            return 0

        created = []

        class App:
            bot = object()

            def create_task(self, coroutine, update=None, *, name=None):
                created.append(coroutine)
                coroutine.close()

        monkeypatch.setattr(
            telegram_bot, "set_bot_start_time", lambda: calls.append("start")
        )
        monkeypatch.setattr(telegram_bot, "set_default_commands", set_default_commands)
        monkeypatch.setattr(
            telegram_bot, "end_all_booking_sessions", end_all_booking_sessions
        )

        await telegram_bot.post_init(App())

        assert calls == ["start", "commands", "bookings"]
        assert [c.__name__ for c in created] == ["startup_sequence"]

    async def test_announcement_before_checker(self, monkeypatch):
        calls = []

        async def announce_new_ui(bot):
            calls.append("announce")
            return 0

        async def check_and_notify(application):
            calls.append("checker")

        monkeypatch.setattr(telegram_bot, "announce_new_ui", announce_new_ui)
        monkeypatch.setattr(telegram_bot, "check_and_notify", check_and_notify)

        await telegram_bot.startup_sequence(
            Application.builder().token("1:test").build()
        )

        assert calls == ["announce", "checker"]


def test_update_type_handler_accepts_updates(application):
    [presence] = application.handlers[-3]
    assert presence.type is Update
