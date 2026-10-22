# ABOUTME: Tests that callbacks without a scheme prefix land on the screens they map to.
# ABOUTME: Find-flow steps (another stream) are replaced by recorders; My watches is real.

import pytest
from sqlmodel import Session, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.commands import find
from src.commands.watches import build_watches_screen
from src.db_models import ServiceSubscription
from src.handlers import text_input
from src.handlers.fallback_callbacks import fallback_callback
from src.i18n import t
from src.repositories import UserRepository, WatchRepository
from src.watches.when import PRESETS
from tests.fakes import FakeBot, FakeContext, make_callback_update

pytestmark = pytest.mark.asyncio

USER = 4242
OLD_MSG = 31
FIND_TEXT = "FIND SCREEN"
FIND_MARKUP = InlineKeyboardMarkup(
    [[InlineKeyboardButton("x", callback_data="f1:all")]]
)


def add_user(db, language="en"):
    with Session(db) as session:
        UserRepository(session).create_user(USER, language=language)


@pytest.fixture(autouse=True)
def pending_input(monkeypatch):
    calls = []
    monkeypatch.setattr(
        text_input, "clear_pending_input", lambda context: calls.append(context)
    )
    return calls


@pytest.fixture
def steps(monkeypatch):
    """Records calls into the find flow"""
    calls = []

    def build_find_screen(lang):
        calls.append(("find", lang))
        return FIND_TEXT, FIND_MARKUP

    async def show_categories(update, context):
        calls.append(("categories",))

    async def show_category_page(update, context, category_id, page):
        calls.append(("category", category_id, page))

    async def show_service_step(update, context, service_id):
        calls.append(("service", service_id))

    async def show_when_step(update, context, service_id, office_id):
        calls.append(("when", service_id, office_id))

    for fn in (
        build_find_screen,
        show_categories,
        show_category_page,
        show_service_step,
        show_when_step,
    ):
        monkeypatch.setattr(find, fn.__name__, fn)
    return calls


async def press(data):
    bot = FakeBot()
    context = FakeContext(bot)
    await fallback_callback(
        make_callback_update(data, message_id=OLD_MSG, bot=bot), context
    )
    return bot, context


@pytest.mark.parametrize("lang", ["en", "ru"])
@pytest.mark.parametrize(
    "data", ["main_menu", "categories", "anything", "srv:abc", "cat:", "catpage:x:y"]
)
async def test_find_screen_in_place(db, steps, pending_input, lang, data):
    add_user(db, lang)

    bot, context = await press(data)

    assert steps == [("find", lang)]
    [edit] = bot.edits
    assert (edit.message_id, edit.text, edit.reply_markup) == (
        OLD_MSG,
        FIND_TEXT,
        FIND_MARKUP,
    )
    assert len(bot.calls_of("answer_callback_query")) == 1
    assert pending_input == [context]
    with Session(db) as session:
        assert UserRepository(session).get_nav_message_id(USER) == OLD_MSG


@pytest.mark.parametrize(
    ("data", "call"),
    [
        ("cat:ausweis", ("category", "ausweis", 0)),
        ("catpage:fahrzeug:2", ("category", "fahrzeug", 2)),
        ("cat:unknown_category", ("categories",)),
        ("catpage:nope:1", ("categories",)),
        ("srv:1063475", ("service", 1063475)),
        ("addsub:1071896", ("service", 1071896)),
        ("selectoffice:1063475:102526", ("when", 1063475, 102526)),
        ("selectoffice:1063475:0", ("when", 1063475, None)),
    ],
)
async def test_find_steps(db, steps, data, call):
    add_user(db)
    bot, _ = await press(data)
    assert steps == [call]
    assert len(bot.calls_of("answer_callback_query")) == 1


@pytest.mark.parametrize(
    "data",
    [
        "myservices",
        "unsub:1063475",
        "unsub_all",
        "unsub_all_confirm",
        "status",
        "setdates",
        "setdates:30",
        "show_stats",
    ],
)
async def test_my_watches_without_changing_data(db, catalog, clock, steps, data):
    add_user(db, "ru")
    with Session(db) as session:
        WatchRepository(session).create_or_update(USER, 1063475, None, PRESETS["asap"])
        session.add(
            ServiceSubscription(user_id=USER, service_id=1063475, office_id=102526)
        )
        session.commit()

    bot, _ = await press(data)

    [edit] = bot.edits
    assert edit.message_id == OLD_MSG
    assert (edit.text, edit.reply_markup) == build_watches_screen(USER, "ru", clock.now)
    assert steps == []
    with Session(db) as session:
        assert WatchRepository(session).count_open(USER) == 1
        assert len(session.exec(select(ServiceSubscription)).all()) == 1


async def test_my_watches_for_unregistered_user(db, steps):
    bot, _ = await press("myservices")
    [edit] = bot.edits
    assert edit.text == t("start.not_registered", "en")
    assert edit.reply_markup is None
