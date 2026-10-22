# ABOUTME: Tests that /help, /menu, /stop, /subscribe and /myservices reply in the user's language.
# ABOUTME: Telegram and the city API are stubbed at the boundary; DB state is real in-memory SQLite.

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from src import database, services_manager
from src.commands import stop as stop_module
from src.commands.help import help_command
from src.commands.menu import menu_command
from src.commands.myservices import myservices_command
from src.commands.stop import stop_command
from src.commands.subscribe import subscribe_command
from src.db_models import ServiceSubscription, User
from src.repositories import SubscriptionRepository, UserRepository

pytestmark = pytest.mark.asyncio

USER_ID = 5151

SERVICES = [
    {"id": 1, "name": "Aufenthaltstitel verlängern"},
    {"id": 2, "name": "Reisepass beantragen für Erwachsene über 24 Jahre"},
]
OFFICES = {
    "offices": [{"id": 10, "name": "Ausländerbehörde München"}],
    "services": [],
    "relations": [],
}


@dataclass
class Sent:
    text: str
    reply_markup: object = None
    parse_mode: str | None = None


@dataclass
class FakeMessage:
    replies: list[Sent] = field(default_factory=list)

    async def reply_text(self, text, reply_markup=None, parse_mode=None, **kwargs):
        self.replies.append(Sent(text, reply_markup, parse_mode))


def make_update():
    message = FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=USER_ID, username="tester"),
        effective_chat=SimpleNamespace(id=USER_ID),
        message=message,
        effective_message=message,
    )


def make_context():
    return SimpleNamespace(user_data={})


def buttons(markup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def reply_of(handler, update=None) -> Sent:
    update = update or make_update()
    await handler(update, make_context())
    assert len(update.message.replies) == 1
    return update.message.replies[0]


@pytest.fixture(autouse=True)
def db(monkeypatch, db_engine):
    monkeypatch.setattr(database, "_engine", db_engine)
    return db_engine


@pytest.fixture(autouse=True)
def city_catalog(monkeypatch):
    monkeypatch.setattr(services_manager, "_services_cache", SERVICES)
    monkeypatch.setattr(services_manager, "_full_payload_cache", OFFICES)


@pytest.fixture
def events(monkeypatch):
    recorded: list[tuple[str, dict]] = []

    async def record(event_name, user_id=None, **properties):
        recorded.append((event_name, {"user_id": user_id, **properties}))

    monkeypatch.setattr(stop_module, "track_event", record)
    return recorded


def add_user(db, language):
    with Session(db) as session:
        UserRepository(session).create_user(
            user_id=USER_ID, username="tester", language=language
        )


def add_subscriptions(db, *service_office_pairs):
    with Session(db) as session:
        repo = SubscriptionRepository(session)
        for service_id, office_id in service_office_pairs:
            repo.add_subscription(USER_ID, service_id, office_id)
        for sub in session.exec(select(ServiceSubscription)).all():
            sub.subscribed_at = datetime(2026, 10, 1, 9, 30)
            session.add(sub)
        session.commit()


HELP_EN = (
    "📚 <b>Help & Documentation</b>\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>🚀 GETTING STARTED</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "1️⃣ <b>Register:</b> Use /start to create your account\n"
    "2️⃣ <b>Set Date Range:</b> Use /setdates to choose when you're available\n"
    "3️⃣ <b>Subscribe:</b> Use /subscribe to select services to monitor\n"
    "4️⃣ <b>Wait:</b> You'll get instant notifications when appointments open up!\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>📝 COMMANDS</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>/start</b> - Register and see welcome message\n"
    "<b>/menu</b> - Show main menu with quick actions\n"
    "<b>/subscribe</b> - Subscribe to appointment services\n"
    "<b>/myservices</b> - View and manage your subscriptions\n"
    "<b>/setdates</b> - Set your preferred date range\n"
    "<b>/status</b> - Check your account status and stats\n"
    "<b>/stop</b> - Unsubscribe from all services and delete data\n"
    "<b>/help</b> - Show this help message\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>💡 KEY CONCEPTS</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>Subscribe vs Book:</b>\n"
    "• <b>Subscribe</b> = Monitor a service for availability\n"
    "• <b>Book</b> = Reserve a specific appointment slot\n\n"
    "<b>Date Range:</b>\n"
    "Set the time period when you're available for appointments. "
    "The bot only searches within your date range.\n\n"
    "<b>Multiple Subscriptions:</b>\n"
    "You can subscribe to multiple services and offices. "
    "The bot monitors all of them simultaneously.\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>🔧 TROUBLESHOOTING</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>Not getting notifications?</b>\n"
    "• Check your subscriptions with /myservices\n"
    "• Verify your date range with /status\n"
    "• Ensure your Telegram notifications are enabled\n\n"
    "<b>Booking fails?</b>\n"
    "• Appointments fill up fast - try booking immediately\n"
    "• Your session may have timed out (15 min limit)\n"
    "• Try booking another available slot\n\n"
    "<b>Can't find my service?</b>\n"
    "• Browse by category in /subscribe\n"
    "• Check if the service name has changed\n"
    "• Some services may not be available for online booking\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>❓ TIPS & BEST PRACTICES</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "✅ Set a realistic date range (e.g., next 3 months)\n"
    "✅ Subscribe to multiple offices for better availability\n"
    "✅ Book immediately when you receive a notification\n"
    "✅ Check your email and confirm within 24 hours\n"
    "✅ Use /status regularly to monitor bot activity\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>🐛 FEEDBACK & BUG REPORTS</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Found a bug or have a suggestion?\n"
    "Report it on GitHub: https://github.com/nkopylov/termin_muenchen_kvr\n\n"
    "We appreciate your feedback! 💙\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
)

USER_COMMANDS = [
    "/start",
    "/menu",
    "/subscribe",
    "/myservices",
    "/setdates",
    "/status",
    "/stop",
    "/help",
]


class TestHelp:
    async def test_english_unchanged(self, db):
        add_user(db, "en")
        sent = await reply_of(help_command)
        assert sent.text == HELP_EN
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [("🏠 Main Menu", "main_menu")]

    async def test_russian(self, db):
        add_user(db, "ru")
        sent = await reply_of(help_command)
        assert sent.text.startswith("📚 <b>Помощь и инструкция</b>\n\n")
        assert "<b>🚀 С ЧЕГО НАЧАТЬ</b>" in sent.text
        assert "/language" not in sent.text
        assert "https://github.com/nkopylov/termin_muenchen_kvr" in sent.text
        assert "Help" not in sent.text
        assert sent.parse_mode == "HTML"
        assert buttons(sent.reply_markup) == [("🏠 Главное меню", "main_menu")]

    @pytest.mark.parametrize("lang", ["en", "ru"])
    async def test_lists_every_user_command_in_order(self, db, lang):
        add_user(db, lang)
        text = (await reply_of(help_command)).text
        positions = [text.index(f"<b>{cmd}</b> - ") for cmd in USER_COMMANDS]
        assert positions == sorted(positions)

    async def test_same_layout_in_both_languages(self, db):
        add_user(db, "en")
        en = (await reply_of(help_command)).text
        with Session(db) as session:
            UserRepository(session).set_language(USER_ID, "ru")
        ru = (await reply_of(help_command)).text
        assert en.count("\n") == ru.count("\n")
        assert en.count("━━━━━━━━━━━━━━━━━━━━") == ru.count("━━━━━━━━━━━━━━━━━━━━")


MENU_BUTTONS_EN = [
    ("📋 Subscribe to available Termins", "categories"),
    ("📊 My Subscriptions", "myservices"),
    ("📅 Set Date Range", "setdates"),
    ("ℹ️ Subscription Status", "status"),
    ("🌐 Language", "language"),
]


class TestMenu:
    async def test_english_unchanged(self, db):
        add_user(db, "en")
        sent = await reply_of(menu_command)
        assert sent.text == "🏠 <b>Main Menu</b>\n\nChoose an action:"
        assert buttons(sent.reply_markup) == MENU_BUTTONS_EN

    async def test_russian(self, db):
        add_user(db, "ru")
        sent = await reply_of(menu_command)
        assert sent.text == "🏠 <b>Главное меню</b>\n\nВыберите действие:"
        assert buttons(sent.reply_markup) == [
            ("📋 Подписаться на свободные записи", "categories"),
            ("📊 Мои подписки", "myservices"),
            ("📅 Указать период дат", "setdates"),
            ("ℹ️ Статус подписки", "status"),
            ("🌐 Язык", "language"),
        ]

    async def test_unregistered_user_english(self):
        sent = await reply_of(menu_command)
        assert sent.text == "👋 Welcome! Please use /start to register first."

    async def test_unregistered_user_with_cached_russian(self):
        update = make_update()
        context = SimpleNamespace(user_data={"lang": "ru"})
        await menu_command(update, context)
        assert update.message.replies[0].text == (
            "👋 Добро пожаловать! Сначала зарегистрируйтесь с помощью /start."
        )


class TestStop:
    async def test_english_unchanged(self, db, events):
        add_user(db, "en")
        add_subscriptions(db, (1, 10), (2, 10))
        sent = await reply_of(stop_command)
        assert sent.text == (
            "👋 You have been unsubscribed and 2 subscription(s) were removed.\n\n"
            "Use /start to register again."
        )

    @pytest.mark.parametrize(
        ("pairs", "removed"),
        [
            ([(1, 10)], "удалена 1 подписка"),
            ([(1, 10), (2, 10)], "удалены 2 подписки"),
            ([], "удалено 0 подписок"),
        ],
    )
    async def test_russian_uses_language_read_before_deletion(
        self, db, events, pairs, removed
    ):
        add_user(db, "ru")
        add_subscriptions(db, *pairs)
        sent = await reply_of(stop_command)
        assert sent.text == (
            f"👋 Вы отписались, {removed}.\n\n"
            "Чтобы зарегистрироваться снова, используйте /start."
        )
        with Session(db) as session:
            assert session.get(User, USER_ID) is None
        assert events[0][0] == "user_stopped"


class TestSubscribe:
    async def test_english_unchanged(self, db):
        add_user(db, "en")
        sent = await reply_of(subscribe_command)
        assert sent.text == (
            "📋 <b>Select a Category:</b>\n\n"
            "Choose a service category to see available services."
        )
        assert buttons(sent.reply_markup)[-1] == ("🏠 Main Menu", "main_menu")

    async def test_english_category_labels_with_id_callbacks(self, db):
        add_user(db, "en")
        sent = await reply_of(subscribe_command)
        assert buttons(sent.reply_markup)[:-1] == [
            ("Ausländerbehörde 🌍 (1)", "cat:auslaenderbehoerde"),
            ("Ausweis & Pass 🆔 (1)", "cat:ausweis"),
        ]

    async def test_russian_translates_category_labels(self, db):
        add_user(db, "ru")
        sent = await reply_of(subscribe_command)
        assert sent.text == (
            "📋 <b>Выберите категорию:</b>\n\n"
            "Выберите категорию услуг, чтобы увидеть доступные услуги."
        )
        assert buttons(sent.reply_markup) == [
            ("Ausländerbehörde 🌍 (1)", "cat:auslaenderbehoerde"),
            ("Паспорт и ID-карта 🆔 (1)", "cat:ausweis"),
            ("🏠 Главное меню", "main_menu"),
        ]


class TestMyServices:
    async def test_empty_english_unchanged(self, db):
        add_user(db, "en")
        sent = await reply_of(myservices_command)
        assert sent.text == (
            "📋 <b>No Subscriptions</b>\n\nYou haven't subscribed to any services yet.\n"
            "Use /subscribe to start monitoring appointment availability!"
        )
        assert buttons(sent.reply_markup) == [
            ("📋 Subscribe to available Termins", "main_menu"),
            ("🏠 Main Menu", "main_menu"),
        ]

    async def test_empty_russian(self, db):
        add_user(db, "ru")
        sent = await reply_of(myservices_command)
        assert sent.text == (
            "📋 <b>Нет подписок</b>\n\nВы пока не подписаны ни на одну услугу.\n"
            "Используйте /subscribe, чтобы начать отслеживать свободные записи!"
        )
        assert buttons(sent.reply_markup) == [
            ("📋 Подписаться на свободные записи", "main_menu"),
            ("🏠 Главное меню", "main_menu"),
        ]

    async def test_list_english_unchanged(self, db):
        add_user(db, "en")
        add_subscriptions(db, (1, 10), (2, 0))
        sent = await reply_of(myservices_command)
        assert sent.text == (
            "📋 <b>Your Subscriptions</b>\n\nYou are monitoring these services:\n\n"
            "• <b>Aufenthaltstitel verlängern</b>\n"
            "   📍 Ausländerbehörde München\n"
            "   📅 Subscribed: 2026-10-01\n\n"
            "• <b>Reisepass beantragen für Erwachsene über 24 Jahre</b>\n"
            "   📍 Unknown Office\n"
            "   📅 Subscribed: 2026-10-01\n\n"
            "<b>Total:</b> 2 subscription(s)"
        )
        assert buttons(sent.reply_markup) == [
            ("🗑 Aufenthaltstitel verlängern", "unsub:1"),
            ("🗑 Reisepass beantragen für Er...", "unsub:2"),
            ("📋 Subscribe to More", "subscribe"),
            ("🗑 Unsubscribe from All", "unsub_all"),
            ("🏠 Main Menu", "main_menu"),
        ]

    async def test_list_russian(self, db):
        add_user(db, "ru")
        add_subscriptions(db, (1, 10), (2, 0))
        sent = await reply_of(myservices_command)
        assert sent.text == (
            "📋 <b>Ваши подписки</b>\n\nВы отслеживаете эти услуги:\n\n"
            "• <b>Aufenthaltstitel verlängern</b>\n"
            "   📍 Ausländerbehörde München\n"
            "   📅 Подписка от: 2026-10-01\n\n"
            "• <b>Reisepass beantragen für Erwachsene über 24 Jahre</b>\n"
            "   📍 Неизвестное отделение\n"
            "   📅 Подписка от: 2026-10-01\n\n"
            "<b>Всего:</b> 2 подписки"
        )
        assert buttons(sent.reply_markup) == [
            ("🗑 Aufenthaltstitel verlängern", "unsub:1"),
            ("🗑 Reisepass beantragen für Er...", "unsub:2"),
            ("📋 Подписаться ещё", "subscribe"),
            ("🗑 Отписаться от всех", "unsub_all"),
            ("🏠 Главное меню", "main_menu"),
        ]

    async def test_russian_total_singular(self, db):
        add_user(db, "ru")
        add_subscriptions(db, (1, 10))
        sent = await reply_of(myservices_command)
        assert sent.text.endswith("<b>Всего:</b> 1 подписка")
