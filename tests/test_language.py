# ABOUTME: Tests for language selection: picker, /start, /language, lang: callbacks and the gate.
# ABOUTME: Telegram objects are stubbed at the boundary; DB state is real (in-memory or temp file SQLite).

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine
from telegram import CallbackQuery, Chat, Message, Update
from telegram import User as TgUser
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    TypeHandler,
)

from src import database
from src.commands import language as language_module
from src.commands import start as start_module
from src.commands.language import (
    bot_commands,
    language_choice_callback,
    language_command,
    language_gate,
    language_menu_callback,
    set_default_commands,
)
from src.commands.menu import menu_command
from src.commands.start import start_command
from src.db_models import User
from src.handlers.buttons import button_callback, show_main_menu
from src.handlers.language_picker import build_language_picker
from src.i18n import t
from src.i18n.user_language import get_user_language, set_user_language
from src.repositories import UserRepository

USER_ID = 4242
CHAT_ID = 4242


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
    answered: bool = False
    edits: list[Sent] = field(default_factory=list)

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(
        self, text, reply_markup=None, parse_mode=None, **kwargs
    ):
        self.edits.append(Sent(text, reply_markup, parse_mode))


@dataclass
class FakeBot:
    sent: list[Sent] = field(default_factory=list)
    command_calls: list[dict] = field(default_factory=list)

    async def send_message(
        self, chat_id, text, reply_markup=None, parse_mode=None, **kwargs
    ):
        assert chat_id == CHAT_ID
        self.sent.append(Sent(text, reply_markup, parse_mode))

    async def set_my_commands(self, commands, scope=None, language_code=None, **kwargs):
        self.command_calls.append(
            {"commands": list(commands), "scope": scope, "language_code": language_code}
        )


def make_update(*, text=None, data=None, language_code="en", user_id=USER_ID):
    message = FakeMessage(text=text) if data is None else None
    query = FakeQuery(data=data) if data is not None else None
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=user_id,
            username="tester",
            first_name="Test",
            language_code=language_code,
        ),
        effective_chat=SimpleNamespace(id=CHAT_ID),
        message=message,
        effective_message=message,
        callback_query=query,
    )


def make_context(user_data=None):
    return SimpleNamespace(
        bot=FakeBot(), user_data={} if user_data is None else user_data
    )


def buttons(markup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


@pytest.fixture(autouse=True)
def db(monkeypatch, db_engine):
    monkeypatch.setattr(database, "_engine", db_engine)
    return db_engine


@pytest.fixture
def events(monkeypatch):
    recorded: list[tuple[str, dict]] = []

    async def record(event_name, user_id=None, **properties):
        recorded.append((event_name, {"user_id": user_id, **properties}))

    monkeypatch.setattr(language_module, "track_event", record)
    monkeypatch.setattr(start_module, "track_event", record)
    return recorded


def add_user(db, language, user_id=USER_ID):
    with Session(db) as session:
        UserRepository(session).create_user(
            user_id=user_id, username="tester", language=language
        )


def stored_language(db, user_id=USER_ID):
    with Session(db) as session:
        user = session.get(User, user_id)
        return None if user is None else user.language


class TestLanguageDefaults:
    def test_repository_creates_users_with_unset_language(self, db_session):
        repo = UserRepository(db_session)
        assert repo.create_user(user_id=1).language == ""
        assert repo.get_or_create_user(user_id=2).language == ""

    def test_set_language(self, db_session):
        repo = UserRepository(db_session)
        repo.create_user(user_id=1)
        assert repo.set_language(1, "ru") is True
        assert repo.get_user(1).language == "ru"

    def test_set_language_unknown_user(self, db_session):
        assert UserRepository(db_session).set_language(999, "ru") is False


class TestUserLanguageHelpers:
    def test_reads_db_and_caches_chosen_language(self, db):
        add_user(db, "ru")
        context = make_context()
        assert get_user_language(USER_ID, context) == "ru"
        assert context.user_data["lang"] == "ru"

    def test_cache_wins_over_db(self, db):
        add_user(db, "en")
        context = make_context({"lang": "ru"})
        assert get_user_language(USER_ID, context) == "ru"

    def test_unset_language_is_english_and_not_cached(self, db):
        add_user(db, "")
        context = make_context()
        assert get_user_language(USER_ID, context) == "en"
        assert "lang" not in context.user_data

    def test_unknown_user_is_english(self):
        assert get_user_language(USER_ID) == "en"

    def test_set_user_language_writes_db_and_cache(self, db):
        add_user(db, "")
        context = make_context()
        set_user_language(USER_ID, "ru", context)
        assert stored_language(db) == "ru"
        assert context.user_data["lang"] == "ru"

    def test_set_user_language_rejects_unsupported(self, db):
        add_user(db, "")
        with pytest.raises(ValueError):
            set_user_language(USER_ID, "de")
        assert stored_language(db) == ""


class TestPicker:
    @pytest.mark.parametrize("code", ["ru", "ru-RU", "uk", "be", "kk", "UK"])
    def test_russian_first_for_russian_likely_users(self, code):
        text, markup = build_language_picker(code)
        assert text == "🌐 Choose your language / Выберите язык"
        assert buttons(markup) == [("🇷🇺 Русский", "lang:ru"), ("🇬🇧 English", "lang:en")]

    @pytest.mark.parametrize("code", ["en", "de", "tr", "", None])
    def test_english_first_otherwise(self, code):
        _, markup = build_language_picker(code)
        assert buttons(markup) == [("🇬🇧 English", "lang:en"), ("🇷🇺 Русский", "lang:ru")]


@pytest.mark.asyncio
class TestStartCommand:
    async def test_new_user_is_created_unset_and_sees_picker(self, db, events):
        update = make_update(text="/start", language_code="ru")
        context = make_context({"lang": "en"})

        await start_command(update, context)

        assert stored_language(db) == ""
        with Session(db) as session:
            user = session.get(User, USER_ID)
            assert user.start_date and user.end_date
        sent = context.bot.sent[-1]
        assert sent.text == t("language.picker_prompt", "en")
        assert buttons(sent.reply_markup)[0] == ("🇷🇺 Русский", "lang:ru")
        assert "lang" not in context.user_data
        assert ("user_registered", {"user_id": USER_ID, "username": "tester"}) in events

    async def test_existing_unset_user_sees_picker(self, db, events):
        add_user(db, "")
        update = make_update(text="/start")
        context = make_context()

        await start_command(update, context)

        assert context.bot.sent[-1].text == t("language.picker_prompt", "en")
        assert update.message.replies == []
        assert stored_language(db) == ""

    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_user_with_language_sees_welcome_in_it(self, db, events, lang):
        add_user(db, lang)
        update = make_update(text="/start")

        await start_command(update, make_context())

        reply = update.message.replies[-1]
        assert reply.text == t("start.welcome", lang)
        assert reply.parse_mode == "HTML"
        assert buttons(reply.reply_markup) == [
            (t("common.btn_main_menu", lang), "main_menu")
        ]

    @pytest.mark.parametrize(("days_ago", "reengaged"), [(40, True), (5, False)])
    async def test_reengagement_measured_against_naive_utc(
        self, db, events, days_ago, reengaged
    ):
        add_user(db, "en")
        with Session(db) as session:
            user = session.get(User, USER_ID)
            user.subscribed_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
                days=days_ago, hours=1
            )
            session.add(user)
            session.commit()

        await start_command(make_update(text="/start"), make_context())

        expected = ("user_reengaged", {"user_id": USER_ID, "days_inactive": days_ago})
        assert (expected in events) is reengaged


@pytest.mark.asyncio
class TestLanguageChoice:
    async def test_first_choice_stores_language_and_shows_welcome(self, db, events):
        add_user(db, "")
        update = make_update(data="lang:ru")
        context = make_context()

        await language_choice_callback(update, context)

        assert stored_language(db) == "ru"
        assert context.user_data["lang"] == "ru"
        assert update.callback_query.answered
        edit = update.callback_query.edits[-1]
        assert edit.text == t("start.welcome", "ru")
        assert edit.parse_mode == "HTML"
        assert buttons(edit.reply_markup) == [("🏠 Главное меню", "main_menu")]
        assert ("language_selected", {"user_id": USER_ID, "language": "ru"}) in events

    async def test_choice_sets_chat_commands_in_that_language(self, db, events):
        add_user(db, "")
        update = make_update(data="lang:ru")
        context = make_context()

        await language_choice_callback(update, context)

        [call] = context.bot.command_calls
        assert call["scope"].chat_id == CHAT_ID
        descriptions = {c.command: c.description for c in call["commands"]}
        assert descriptions["language"] == "Сменить язык"
        assert descriptions["start"] == t("commands.start", "ru")

    async def test_switching_shows_confirmation(self, db, events):
        add_user(db, "en")
        update = make_update(data="lang:ru")
        context = make_context({"lang": "en"})

        await language_choice_callback(update, context)

        assert stored_language(db) == "ru"
        assert context.user_data["lang"] == "ru"
        edit = update.callback_query.edits[-1]
        assert edit.text == t("language.changed", "ru")
        assert buttons(edit.reply_markup) == [("🏠 Главное меню", "main_menu")]

    async def test_switching_back_to_english(self, db, events):
        add_user(db, "ru")
        update = make_update(data="lang:en")

        await language_choice_callback(update, make_context())

        assert stored_language(db) == "en"
        assert update.callback_query.edits[-1].text == t("language.changed", "en")

    async def test_unknown_user_is_registered_with_choice(self, db, events):
        update = make_update(data="lang:en")

        await language_choice_callback(update, make_context())

        assert stored_language(db) == "en"
        assert update.callback_query.edits[-1].text == t("start.welcome", "en")
        assert any(name == "user_registered" for name, _ in events)

    async def test_unsupported_language_is_ignored(self, db, events):
        add_user(db, "")
        update = make_update(data="lang:de")
        context = make_context()

        await language_choice_callback(update, context)

        assert stored_language(db) == ""
        assert update.callback_query.answered
        assert update.callback_query.edits == []
        assert context.bot.command_calls == []

    async def test_choice_survives_command_list_failure(self, db, events, caplog):
        add_user(db, "")
        update = make_update(data="lang:ru")
        context = make_context()

        async def fail(*args, **kwargs):
            raise TelegramError("network down")

        context.bot.set_my_commands = fail

        with caplog.at_level(logging.WARNING, logger="src.commands.language"):
            await language_choice_callback(update, context)

        assert stored_language(db) == "ru"
        assert update.callback_query.edits[-1].text == t("start.welcome", "ru")
        assert any("network down" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
class TestLanguageCommand:
    async def test_command_shows_picker(self, db):
        add_user(db, "en")
        update = make_update(text="/language", language_code="uk")
        context = make_context()

        await language_command(update, context)

        sent = context.bot.sent[-1]
        assert sent.text == t("language.picker_prompt", "en")
        assert buttons(sent.reply_markup)[0] == ("🇷🇺 Русский", "lang:ru")

    async def test_menu_button_shows_picker(self, db):
        add_user(db, "ru")
        update = make_update(data="language")

        await language_menu_callback(update, make_context())

        assert update.callback_query.answered
        edit = update.callback_query.edits[-1]
        assert edit.text == t("language.picker_prompt", "en")
        assert buttons(edit.reply_markup)[0] == ("🇬🇧 English", "lang:en")


@pytest.mark.asyncio
class TestMainMenuLanguageButton:
    @pytest.mark.parametrize(
        ("lang", "label"), [("en", "🌐 Language"), ("ru", "🌐 Язык")]
    )
    async def test_menu_command_has_language_button(self, db, lang, label):
        add_user(db, lang)
        update = make_update(text="/menu")

        await menu_command(update, make_context())

        assert (label, "language") in buttons(update.message.replies[-1].reply_markup)

    async def test_inline_main_menu_has_language_button(self, db):
        add_user(db, "ru")
        query = FakeQuery(data="main_menu")

        await show_main_menu(query, USER_ID)

        assert ("🌐 Язык", "language") in buttons(query.edits[-1].reply_markup)


@pytest.mark.asyncio
class TestGate:
    async def test_unset_user_message_gets_picker_and_stops(self, db):
        add_user(db, "")
        update = make_update(text="/menu", language_code="ru")
        context = make_context()

        with pytest.raises(ApplicationHandlerStop):
            await language_gate(update, context)

        sent = context.bot.sent[-1]
        assert sent.text == t("language.picker_prompt", "en")
        assert buttons(sent.reply_markup)[0] == ("🇷🇺 Русский", "lang:ru")

    async def test_unset_user_callback_is_answered_then_stopped(self, db):
        add_user(db, "")
        update = make_update(data="main_menu")
        context = make_context()

        with pytest.raises(ApplicationHandlerStop):
            await language_gate(update, context)

        assert update.callback_query.answered
        assert update.callback_query.edits == []
        assert context.bot.sent[-1].text == t("language.picker_prompt", "en")

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"text": "/start"},
            {"text": "/start@MuenchenTerminBot"},
            {"text": "/language"},
            {"data": "lang:ru"},
            {"data": "language"},
        ],
    )
    async def test_unset_user_can_reach_language_flow(self, db, kwargs):
        add_user(db, "")
        context = make_context()

        assert await language_gate(make_update(**kwargs), context) is None
        assert context.bot.sent == []

    async def test_similar_command_is_still_gated(self, db):
        add_user(db, "")
        with pytest.raises(ApplicationHandlerStop):
            await language_gate(make_update(text="/startx"), make_context())

    async def test_unknown_user_passes_untouched(self, db):
        context = make_context()

        assert await language_gate(make_update(text="/menu"), context) is None
        assert context.bot.sent == []
        assert stored_language(db) is None

    async def test_user_with_language_passes_and_is_cached(self, db):
        add_user(db, "ru")
        context = make_context()

        assert await language_gate(make_update(text="/menu"), context) is None
        assert context.bot.sent == []
        assert context.user_data["lang"] == "ru"

    async def test_update_without_user_passes(self):
        update = SimpleNamespace(effective_user=None, message=None, callback_query=None)
        assert await language_gate(update, make_context()) is None


class TestBotCommands:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_command_list(self, lang):
        commands = bot_commands(lang)
        assert [c.command for c in commands] == [
            "start",
            "menu",
            "subscribe",
            "myservices",
            "setdates",
            "status",
            "help",
            "language",
            "stop",
        ]
        for command in commands:
            assert command.description == t(f"commands.{command.command}", lang)
            assert 1 <= len(command.description) <= 256

    @pytest.mark.asyncio
    async def test_default_commands_english_plus_russian(self):
        bot = FakeBot()
        await set_default_commands(bot)

        by_code = {call["language_code"]: call for call in bot.command_calls}
        assert set(by_code) == {None, "ru"}
        assert by_code[None]["commands"] == bot_commands("en")
        assert by_code["ru"]["commands"] == bot_commands("ru")


class TestHandlerRegistration:
    @staticmethod
    def _callback_update(data: str) -> Update:
        user = TgUser(id=USER_ID, first_name="Test", is_bot=False)
        return Update(
            update_id=1,
            callback_query=CallbackQuery(
                id="1",
                from_user=user,
                chat_instance="c",
                data=data,
                message=Message(
                    message_id=1, date=None, chat=Chat(id=CHAT_ID, type="private")
                ),
            ),
        )

    @pytest.fixture
    def application(self):
        from telegram_bot import register_handlers

        app = Application.builder().token("1:test").build()
        register_handlers(app)
        return app

    def _first_match(self, application, update):
        for handler in application.handlers[0]:
            if handler.check_update(update):
                return handler
        return None

    def test_gate_runs_before_all_other_handlers(self, application):
        assert min(application.handlers) == -1
        [gate] = application.handlers[-1]
        assert isinstance(gate, TypeHandler)
        assert gate.callback is language_gate

    @pytest.mark.parametrize(
        ("data", "callback"),
        [
            ("lang:ru", language_choice_callback),
            ("language", language_menu_callback),
            ("main_menu", button_callback),
        ],
    )
    def test_callbacks_route_to_expected_handler(self, application, data, callback):
        handler = self._first_match(application, self._callback_update(data))
        assert isinstance(handler, CallbackQueryHandler)
        assert handler.callback is callback

    def test_language_command_registered(self, application):
        assert any(
            isinstance(h, CommandHandler)
            and h.commands == frozenset({"language"})
            and h.callback is language_command
            for h in application.handlers[0]
        )


class TestLanguageResetMigration:
    @staticmethod
    def _user_version(engine) -> int:
        with engine.connect() as conn:
            return conn.execute(text("PRAGMA user_version")).scalar()

    def test_resets_existing_users_exactly_once(self, monkeypatch, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'bot.db'}")
        monkeypatch.setattr(database, "_engine", engine)
        SQLModel.metadata.create_all(engine)
        add_user(engine, "de", user_id=1)
        add_user(engine, "en", user_id=2)

        database.init_database()

        assert stored_language(engine, 1) == ""
        assert stored_language(engine, 2) == ""
        assert self._user_version(engine) == 1

        with Session(engine) as session:
            UserRepository(session).set_language(1, "ru")
        database.init_database()

        assert stored_language(engine, 1) == "ru"
        assert self._user_version(engine) == 1

    def test_fresh_database_is_marked_migrated(self, monkeypatch, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
        monkeypatch.setattr(database, "_engine", engine)

        database.init_database()
        add_user(engine, "ru", user_id=1)
        database.init_database()

        assert self._user_version(engine) == 1
        assert stored_language(engine, 1) == "ru"
