# ABOUTME: Tests that taps on the reply keyboard reach the right screen in either language
# ABOUTME: and clear a pending typed-date answer. Real in-memory DB, recording FakeBot.

import pytest
from sqlmodel import Session

from src.commands import find
from src.commands.settings import build_settings_screen
from src.handlers import text_input
from src.handlers.menu_keyboard import menu_text
from src.i18n import t
from src.repositories import UserRepository
from tests.fakes import FakeBot, FakeContext, make_text_update

pytestmark = pytest.mark.asyncio

USER = 4242


def add_user(db, language):
    with Session(db) as session:
        UserRepository(session).create_user(USER, language=language)


@pytest.fixture(autouse=True)
def pending_input(monkeypatch):
    """clear_pending_input belongs to the find stream; record calls and drop the key"""
    calls = []

    def clear(context):
        calls.append(context)
        context.user_data.pop(text_input.AWAIT_KEY, None)

    monkeypatch.setattr(text_input, "clear_pending_input", clear)
    return calls


@pytest.fixture
def find_calls(monkeypatch):
    calls = []

    async def find_command(update, context):
        calls.append(update.message.text)

    monkeypatch.setattr(find, "find_command", find_command)
    return calls


async def tap(label):
    bot = FakeBot()
    context = FakeContext(bot, user_data={text_input.AWAIT_KEY: {"kind": "before"}})
    await menu_text(make_text_update(label, bot=bot), context)
    return bot, context


@pytest.mark.parametrize("label_lang", ["en", "ru"])
@pytest.mark.parametrize("user_lang", ["en", "ru"])
class TestRouting:
    async def test_find(self, db, catalog, find_calls, label_lang, user_lang):
        add_user(db, user_lang)
        label = t("keyboard.find", label_lang)
        _, context = await tap(label)
        assert find_calls == [label]
        assert text_input.AWAIT_KEY not in context.user_data

    async def test_watches(self, db, catalog, clock, find_calls, label_lang, user_lang):
        add_user(db, user_lang)
        bot, context = await tap(t("keyboard.watches", label_lang))
        assert [s.text for s in bot.sent] == [t("watches.empty", user_lang)]
        assert text_input.AWAIT_KEY not in context.user_data
        assert find_calls == []

    async def test_settings(self, db, find_calls, label_lang, user_lang):
        add_user(db, user_lang)
        bot, context = await tap(t("keyboard.settings", label_lang))
        [sent] = bot.sent
        assert (sent.text, sent.reply_markup) == build_settings_screen(USER, user_lang)
        assert text_input.AWAIT_KEY not in context.user_data

    async def test_help(self, db, find_calls, label_lang, user_lang):
        add_user(db, user_lang)
        bot, context = await tap(t("keyboard.help", label_lang))
        assert [s.text for s in bot.sent] == [
            t("help.text", user_lang, find=t("keyboard.find", user_lang))
        ]
        assert text_input.AWAIT_KEY not in context.user_data


async def test_label_with_surrounding_spaces(db, find_calls):
    add_user(db, "en")
    await tap(f"  {t('keyboard.find', 'en')} ")
    assert len(find_calls) == 1


async def test_unknown_text_does_nothing(db, find_calls, pending_input):
    add_user(db, "en")
    bot, context = await tap("hello")
    assert bot.calls == []
    assert find_calls == []
    assert text_input.AWAIT_KEY in context.user_data
