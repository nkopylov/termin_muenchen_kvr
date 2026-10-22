# ABOUTME: Tests the English and Russian output of the inline button screens and category labels.
# ABOUTME: The city API payload and Telegram query are stubbed; DB state is a real in-memory SQLite.

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from src import database, services_manager
from src.config import get_config
from src.db_models import AppointmentLog
from src.handlers import buttons as buttons_module
from src.handlers.buttons import button_callback, show_main_menu
from src.i18n import t
from src.repositories import (
    BookingSessionRepository,
    SubscriptionRepository,
    UserRepository,
)
from src.services import appointment_checker
from src.services_manager import (
    CATEGORY_KEYWORDS,
    categorize_services,
    get_category_for_service,
)

USER_ID = 5151
START = "2026-11-01"
END = "2026-12-31"

ENGLISH_LABELS = {
    "auslaenderbehoerde": "Ausländerbehörde 🌍",
    "ausweis": "Ausweis & Pass 🆔",
    "fahrzeug": "Fahrzeug 🚗",
    "fuehrerschein": "Führerschein 🪪",
    "wohnsitz": "Wohnsitz 🏠",
    "gewerbe": "Gewerbe 💼",
    "familie": "Familie 👨‍👩‍👧",
    "soziales": "Rente & Soziales 🏥",
    "parken": "Parken 🅿️",
    "sonstiges": "Sonstiges 📋",
}

SERVICES = [
    {"id": 1, "name": "Aufenthaltstitel - Verlängerung", "maxQuantity": 1},
    {"id": 2, "name": "Kfz-Zulassung", "maxQuantity": 3},
    {"id": 3, "name": "Hundesteuer"},
    *[
        {"id": 100 + i, "name": f"Führerschein Klasse {i:02d}", "maxQuantity": 1}
        for i in range(11)
    ],
]
OFFICES = [
    {"id": 10, "name": "Ausländerbehörde Ruppertstraße"},
    {"id": 11},
    *[{"id": 200 + i, "name": f"Bürgerbüro {i:02d}"} for i in range(21)],
]
RELATIONS = [
    {"officeId": 10, "serviceId": 1, "public": True},
    {"officeId": 11, "serviceId": 1, "public": True},
    *[{"officeId": 200 + i, "serviceId": 3, "public": True} for i in range(21)],
]


@dataclass
class Edit:
    text: str
    reply_markup: object = None
    parse_mode: str | None = None


@dataclass
class FakeQuery:
    data: str
    answers: list[tuple[str | None, bool]] = field(default_factory=list)
    edits: list[Edit] = field(default_factory=list)

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append((text, show_alert))

    async def edit_message_text(
        self, text, reply_markup=None, parse_mode=None, **kwargs
    ):
        self.edits.append(Edit(text, reply_markup, parse_mode))

    @property
    def last(self) -> Edit:
        return self.edits[-1]


def buttons(markup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def press(data: str, context=None) -> FakeQuery:
    query = FakeQuery(data=data)
    update = SimpleNamespace(
        callback_query=query, effective_user=SimpleNamespace(id=USER_ID)
    )
    await button_callback(update, context or SimpleNamespace(user_data={}))
    return query


@pytest.fixture(autouse=True)
def db(monkeypatch, db_engine):
    monkeypatch.setattr(database, "_engine", db_engine)
    return db_engine


@pytest.fixture(autouse=True)
def city_catalog(monkeypatch):
    monkeypatch.setattr(services_manager, "_services_cache", SERVICES)
    monkeypatch.setattr(
        services_manager,
        "_full_payload_cache",
        {"services": SERVICES, "offices": OFFICES, "relations": RELATIONS},
    )


@pytest.fixture(autouse=True)
def events(monkeypatch):
    recorded: list[tuple[str, dict]] = []

    async def record(event_name, user_id=None, **properties):
        recorded.append((event_name, {"user_id": user_id, **properties}))

    monkeypatch.setattr(buttons_module, "track_event", record)
    return recorded


@pytest.fixture
def check_stats(monkeypatch):
    def set_last_check(value):
        monkeypatch.setitem(appointment_checker.stats, "last_check_time", value)

    set_last_check(None)
    return set_last_check


def add_user(db, lang):
    with Session(db) as session:
        UserRepository(session).create_user(
            user_id=USER_ID,
            username="tester",
            language=lang,
            start_date=START,
            end_date=END,
        )


def subscribe(db, service_id, office_id):
    with Session(db) as session:
        SubscriptionRepository(session).add_subscription(USER_ID, service_id, office_id)


def subscription_dates(db) -> list[str]:
    with Session(db) as session:
        subs = SubscriptionRepository(session).get_user_subscriptions(USER_ID)
        return [s["subscribed_at"][:10] for s in subs]


class TestCategoryIds:
    def test_category_ids_are_short_ascii(self):
        assert list(CATEGORY_KEYWORDS) == list(ENGLISH_LABELS)
        for category_id in CATEGORY_KEYWORDS:
            assert category_id.isascii()
            assert len(f"catpage:{category_id}:999".encode()) <= 64

    def test_categorize_services_is_keyed_by_id(self):
        categories = categorize_services()
        assert [s["id"] for s in categories["auslaenderbehoerde"]] == [1]
        assert [s["id"] for s in categories["fahrzeug"]] == [2]
        assert [s["id"] for s in categories["sonstiges"]] == [3]
        assert len(categories["fuehrerschein"]) == 11
        assert set(categories) <= set(CATEGORY_KEYWORDS)

    def test_category_for_service_is_id(self):
        assert get_category_for_service(2) == "fahrzeug"
        assert get_category_for_service(3) == "sonstiges"
        assert get_category_for_service(999) is None

    def test_english_labels_unchanged(self):
        for category_id, label in ENGLISH_LABELS.items():
            assert t(f"categories.{category_id}", "en") == label

    def test_russian_labels(self):
        assert {cid: t(f"categories.{cid}", "ru") for cid in CATEGORY_KEYWORDS} == {
            "auslaenderbehoerde": "Ausländerbehörde 🌍",
            "ausweis": "Паспорт и ID-карта 🆔",
            "fahrzeug": "Автомобиль 🚗",
            "fuehrerschein": "Водительские права 🪪",
            "wohnsitz": "Место жительства 🏠",
            "gewerbe": "Бизнес 💼",
            "familie": "Семья 👨‍👩‍👧",
            "soziales": "Пенсия и соцпомощь 🏥",
            "parken": "Парковка 🅿️",
            "sonstiges": "Другое 📋",
        }


@pytest.mark.asyncio
class TestMainMenu:
    async def test_english(self, db):
        add_user(db, "en")
        query = await press("main_menu")
        assert query.last.text == "🏠 <b>Main Menu</b>\n\nChoose an action:"
        assert buttons(query.last.reply_markup) == [
            ("📋 Subscribe to available Termins", "categories"),
            ("📊 My Subscriptions", "myservices"),
            ("📅 Set Date Range", "setdates"),
            ("ℹ️ Subscription Status", "status"),
            ("🌐 Language", "language"),
        ]

    async def test_russian(self, db):
        add_user(db, "ru")
        query = await press("main_menu")
        assert query.last.text == "🏠 <b>Главное меню</b>\n\nВыберите действие:"
        assert buttons(query.last.reply_markup) == [
            ("📋 Подписаться на свободные записи", "categories"),
            ("📊 Мои подписки", "myservices"),
            ("📅 Выбрать период дат", "setdates"),
            ("ℹ️ Статус подписки", "status"),
            ("🌐 Язык", "language"),
        ]

    async def test_cached_language_is_used(self, db):
        add_user(db, "en")
        query = await press("main_menu", SimpleNamespace(user_data={"lang": "ru"}))
        assert query.last.text.startswith("🏠 <b>Главное меню</b>")

    async def test_helper_without_lang_reads_db(self, db):
        add_user(db, "ru")
        query = FakeQuery(data="main_menu")
        await show_main_menu(query, USER_ID)
        assert query.last.text.startswith("🏠 <b>Главное меню</b>")


@pytest.mark.asyncio
class TestCategoryList:
    async def test_english(self, db):
        add_user(db, "en")
        query = await press("categories")
        assert query.last.text == "📋 <b>Select a Category:</b>"
        assert buttons(query.last.reply_markup) == [
            ("Ausländerbehörde 🌍 (1)", "cat:auslaenderbehoerde"),
            ("Fahrzeug 🚗 (1)", "cat:fahrzeug"),
            ("Sonstiges 📋 (1)", "cat:sonstiges"),
            ("Führerschein 🪪 (11)", "cat:fuehrerschein"),
        ]

    async def test_russian(self, db):
        add_user(db, "ru")
        query = await press("categories")
        assert query.last.text == "📋 <b>Выберите категорию:</b>"
        assert buttons(query.last.reply_markup) == [
            ("Ausländerbehörde 🌍 (1)", "cat:auslaenderbehoerde"),
            ("Автомобиль 🚗 (1)", "cat:fahrzeug"),
            ("Другое 📋 (1)", "cat:sonstiges"),
            ("Водительские права 🪪 (11)", "cat:fuehrerschein"),
        ]


@pytest.mark.asyncio
class TestCategoryServices:
    async def test_first_page_english(self, db):
        add_user(db, "en")
        query = await press("cat:fuehrerschein")
        assert (
            query.last.text == "<b>Führerschein 🪪</b>\n\nShowing 1-10 of 11 services"
        )
        assert buttons(query.last.reply_markup)[-2:] == [
            ("🏠 Main Menu", "main_menu"),
            ("Next ▶️", "catpage:fuehrerschein:1"),
        ]

    async def test_first_page_russian(self, db):
        add_user(db, "ru")
        query = await press("cat:fuehrerschein")
        assert query.last.text == "<b>Водительские права 🪪</b>\n\nУслуги 1–10 из 11"
        assert buttons(query.last.reply_markup)[0] == (
            "Führerschein Klasse 00",
            "srv:100",
        )
        assert buttons(query.last.reply_markup)[-2:] == [
            ("🏠 Меню", "main_menu"),
            ("Далее ▶️", "catpage:fuehrerschein:1"),
        ]

    async def test_second_page(self, db):
        add_user(db, "en")
        query = await press("catpage:fuehrerschein:1")
        assert (
            query.last.text == "<b>Führerschein 🪪</b>\n\nShowing 11-11 of 11 services"
        )
        assert buttons(query.last.reply_markup)[-2:] == [
            ("◀️ Previous", "catpage:fuehrerschein:0"),
            ("🏠 Main Menu", "main_menu"),
        ]

        add_user_lang(db, "ru")
        query = await press("catpage:fuehrerschein:1")
        assert query.last.text == "<b>Водительские права 🪪</b>\n\nУслуги 11–11 из 11"
        assert buttons(query.last.reply_markup)[-2:] == [
            ("◀️ Назад", "catpage:fuehrerschein:0"),
            ("🏠 Меню", "main_menu"),
        ]

    async def test_empty_category(self, db):
        add_user(db, "en")
        query = await press("cat:parken")
        assert query.last.text == "❌ No services found in Parken 🅿️ category."

        add_user_lang(db, "ru")
        query = await press("cat:parken")
        assert query.last.text == "❌ В категории «Парковка 🅿️» услуги не найдены."

    @pytest.mark.parametrize(
        "data", ["cat:Fahrzeug 🚗", "catpage:Fahrzeug 🚗:1", "cat:nope"]
    )
    async def test_unknown_category_shows_category_list(self, db, data):
        add_user(db, "ru")
        query = await press(data)
        assert query.last.text == "📋 <b>Выберите категорию:</b>"
        assert ("Автомобиль 🚗 (1)", "cat:fahrzeug") in buttons(query.last.reply_markup)


def add_user_lang(db, lang):
    with Session(db) as session:
        UserRepository(session).set_language(USER_ID, lang)


@pytest.mark.asyncio
class TestServiceDetails:
    async def test_not_subscribed_english(self, db):
        add_user(db, "en")
        query = await press("srv:2")
        assert query.last.text == (
            "<b>Kfz-Zulassung</b>\n\n"
            "Service ID: <code>2</code>\n"
            "Max. Quantity: 3\n"
            "\nStatus: ⭕ Not subscribed"
        )
        assert buttons(query.last.reply_markup) == [
            ("✅ Subscribe", "addsub:2"),
            ("◀️ Back", "cat:fahrzeug"),
            ("🏠 Categories", "categories"),
        ]

    async def test_not_subscribed_russian(self, db):
        add_user(db, "ru")
        query = await press("srv:2")
        assert query.last.text == (
            "<b>Kfz-Zulassung</b>\n\n"
            "ID услуги: <code>2</code>\n"
            "Макс. количество: 3\n"
            "\nСтатус: ⭕ Нет подписки"
        )
        assert buttons(query.last.reply_markup) == [
            ("✅ Подписаться", "addsub:2"),
            ("◀️ Назад", "cat:fahrzeug"),
            ("🏠 Категории", "categories"),
        ]

    async def test_subscribed(self, db):
        add_user(db, "en")
        subscribe(db, 3, 200)
        query = await press("srv:3")
        assert query.last.text == (
            "<b>Hundesteuer</b>\n\nService ID: <code>3</code>\n\nStatus: ✅ Subscribed"
        )
        assert buttons(query.last.reply_markup)[0] == ("🗑 Unsubscribe", "unsub:3")

        add_user_lang(db, "ru")
        query = await press("srv:3")
        assert query.last.text == (
            "<b>Hundesteuer</b>\n\nID услуги: <code>3</code>\n\nСтатус: ✅ Подписка оформлена"
        )
        assert buttons(query.last.reply_markup)[0] == ("🗑 Отписаться", "unsub:3")

    async def test_service_not_found(self, db):
        add_user(db, "en")
        assert (await press("srv:999")).last.text == "❌ Service not found."
        add_user_lang(db, "ru")
        assert (await press("srv:999")).last.text == "❌ Услуга не найдена."


@pytest.mark.asyncio
class TestOfficeSelection:
    async def test_english(self, db):
        add_user(db, "en")
        query = await press("addsub:1")
        assert query.last.text == (
            "<b>Aufenthaltstitel - Verlängerung</b>\n\n"
            "📍 Please select an office:\n(2 available)"
        )
        assert buttons(query.last.reply_markup) == [
            ("📍 Ausländerbehörde Ruppertstraße", "selectoffice:1:10"),
            ("📍 Office 11", "selectoffice:1:11"),
            ("◀️ Back", "srv:1"),
        ]

    async def test_russian(self, db):
        add_user(db, "ru")
        query = await press("addsub:1")
        assert query.last.text == (
            "<b>Aufenthaltstitel - Verlängerung</b>\n\n"
            "📍 Выберите отделение:\n(доступно: 2)"
        )
        assert buttons(query.last.reply_markup) == [
            ("📍 Ausländerbehörde Ruppertstraße", "selectoffice:1:10"),
            ("📍 Отделение 11", "selectoffice:1:11"),
            ("◀️ Назад", "srv:1"),
        ]

    async def test_more_than_twenty_offices(self, db):
        add_user(db, "en")
        query = await press("addsub:3")
        assert query.last.text.endswith(
            "(21 available)\n\n⚠️ Only the first 20 of 21 offices are shown."
        )
        assert len(buttons(query.last.reply_markup)) == 21

        add_user_lang(db, "ru")
        query = await press("addsub:3")
        assert query.last.text.endswith(
            "(доступно: 21)\n\n⚠️ Показаны только первые 20 отделений (всего: 21)."
        )

    async def test_no_offices(self, db):
        add_user(db, "en")
        query = await press("addsub:2")
        assert query.last.text == "❌ No offices found for 'Kfz-Zulassung'."
        assert buttons(query.last.reply_markup) == [("◀️ Back", "srv:2")]

        add_user_lang(db, "ru")
        query = await press("addsub:2")
        assert (
            query.last.text == "❌ Для «Kfz-Zulassung» не найдено ни одного отделения."
        )
        assert buttons(query.last.reply_markup) == [("◀️ Назад", "srv:2")]

    async def test_service_not_found(self, db):
        add_user(db, "ru")
        assert (await press("addsub:999")).last.text == "❌ Услуга не найдена."


@pytest.mark.asyncio
class TestSelectOffice:
    async def test_english(self, db, events):
        add_user(db, "en")
        query = await press("selectoffice:1:10")
        assert query.last.text == (
            "🎉 <b>Subscription Successful!</b>\n\n"
            "<b>Aufenthaltstitel - Verlängerung</b>\n"
            "📍 Office: Ausländerbehörde Ruppertstraße\n\n"
            "📅 You will receive notifications when appointments become available "
            f"between <b>{START}</b> and <b>{END}</b>.\n\n"
            "💡 Tip: Use /setdates to change your date range anytime!"
        )
        assert buttons(query.last.reply_markup) == [
            ("📊 My Subscriptions", "myservices"),
            ("🏠 Main Menu", "main_menu"),
        ]
        assert events[-1][0] == "subscription_added"

    async def test_russian(self, db):
        add_user(db, "ru")
        query = await press("selectoffice:1:10")
        assert query.last.text == (
            "🎉 <b>Подписка оформлена!</b>\n\n"
            "<b>Aufenthaltstitel - Verlängerung</b>\n"
            "📍 Отделение: Ausländerbehörde Ruppertstraße\n\n"
            "📅 Вы получите уведомление, когда появятся свободные записи "
            f"в период с <b>{START}</b> по <b>{END}</b>.\n\n"
            "💡 Совет: период дат можно изменить в любой момент командой /setdates!"
        )
        assert buttons(query.last.reply_markup) == [
            ("📊 Мои подписки", "myservices"),
            ("🏠 Главное меню", "main_menu"),
        ]

    @pytest.mark.parametrize(
        ("lang", "line"),
        [("en", "📍 Office: Office 11\n"), ("ru", "📍 Отделение: Отделение 11\n")],
    )
    async def test_office_without_name(self, db, lang, line):
        add_user(db, lang)
        query = await press("selectoffice:1:11")
        assert line in query.last.text


@pytest.mark.asyncio
class TestUnsubscribe:
    async def test_alert_then_details(self, db, events):
        add_user(db, "ru")
        subscribe(db, 2, 10)
        query = await press("unsub:2")
        assert query.answers[-1] == ("🗑 Подписка отменена", True)
        assert query.last.text.endswith("Статус: ⭕ Нет подписки")
        assert events[-1][0] == "subscription_removed"

    async def test_english_alert(self, db):
        add_user(db, "en")
        subscribe(db, 2, 10)
        query = await press("unsub:2")
        assert query.answers[-1] == ("🗑 Unsubscribed", True)


@pytest.mark.asyncio
class TestMyServices:
    async def test_empty_english(self, db):
        add_user(db, "en")
        query = await press("myservices")
        assert query.last.text == (
            "📋 <b>No Subscriptions</b>\n\nYou haven't subscribed to any services yet.\n"
            "Use /subscribe to start monitoring appointment availability!"
        )
        assert buttons(query.last.reply_markup) == [("🏠 Main Menu", "main_menu")]

    async def test_empty_russian(self, db):
        add_user(db, "ru")
        query = await press("myservices")
        assert query.last.text == (
            "📋 <b>Нет подписок</b>\n\nВы пока не подписаны ни на одну услугу.\n"
            "Используйте /subscribe, чтобы начать отслеживать свободные записи!"
        )
        assert buttons(query.last.reply_markup) == [("🏠 Главное меню", "main_menu")]

    async def test_list_english(self, db):
        add_user(db, "en")
        subscribe(db, 1, 10)
        subscribe(db, 2, 0)
        day1, day2 = subscription_dates(db)
        query = await press("myservices")
        assert query.last.text == (
            "📋 <b>Your Subscriptions</b>\n\nYou are monitoring these services:\n\n"
            "• <b>Aufenthaltstitel - Verlängerung</b>\n"
            "   📍 Ausländerbehörde Ruppertstraße\n"
            f"   📅 Subscribed: {day1}\n\n"
            "• <b>Kfz-Zulassung</b>\n"
            "   📍 Unknown Office\n"
            f"   📅 Subscribed: {day2}\n\n"
            "<b>Total:</b> 2 subscription(s)"
        )
        assert buttons(query.last.reply_markup) == [
            ("🗑 Aufenthaltstitel - Verlängerung", "unsub:1"),
            ("🗑 Kfz-Zulassung", "unsub:2"),
            ("🗑 Unsubscribe from All", "unsub_all"),
            ("🏠 Main Menu", "main_menu"),
        ]

    async def test_list_russian(self, db):
        add_user(db, "ru")
        subscribe(db, 1, 10)
        subscribe(db, 2, 0)
        day1, day2 = subscription_dates(db)
        query = await press("myservices")
        assert query.last.text == (
            "📋 <b>Ваши подписки</b>\n\nВы отслеживаете эти услуги:\n\n"
            "• <b>Aufenthaltstitel - Verlängerung</b>\n"
            "   📍 Ausländerbehörde Ruppertstraße\n"
            f"   📅 Подписка оформлена: {day1}\n\n"
            "• <b>Kfz-Zulassung</b>\n"
            "   📍 Неизвестное отделение\n"
            f"   📅 Подписка оформлена: {day2}\n\n"
            "<b>Всего:</b> 2 подписки"
        )
        assert buttons(query.last.reply_markup)[-2:] == [
            ("🗑 Отписаться от всех", "unsub_all"),
            ("🏠 Главное меню", "main_menu"),
        ]

    @pytest.mark.parametrize(
        ("lang", "first", "second"),
        [
            ("en", "   📍 Office 11\n", "   📍 Office 99\n"),
            ("ru", "   📍 Отделение 11\n", "   📍 Отделение 99\n"),
        ],
    )
    async def test_office_name_fallback(self, db, lang, first, second):
        add_user(db, lang)
        subscribe(db, 1, 11)
        subscribe(db, 2, 99)
        query = await press("myservices")
        assert first in query.last.text
        assert second in query.last.text


class TestOfficeNameFallback:
    @pytest.mark.parametrize("office_id", [11, 99])
    def test_without_language_is_english(self, office_id):
        assert services_manager.get_office_name(office_id) == f"Office {office_id}"

    @pytest.mark.parametrize(
        ("lang", "office_id", "name"),
        [
            ("en", 11, "Office 11"),
            ("en", 99, "Office 99"),
            ("ru", 11, "Отделение 11"),
            ("ru", 99, "Отделение 99"),
        ],
    )
    def test_localized(self, lang, office_id, name):
        assert services_manager.get_office_name(office_id, lang) == name

    @pytest.mark.parametrize("lang", [None, "en", "ru"])
    def test_named_office_is_city_data(self, lang):
        assert (
            services_manager.get_office_name(10, lang)
            == "Ausländerbehörde Ruppertstraße"
        )


@pytest.mark.asyncio
class TestUnsubscribeAll:
    async def test_confirmation_english(self, db):
        add_user(db, "en")
        query = await press("unsub_all")
        assert query.last.text == (
            "⚠️ <b>Unsubscribe from All Services?</b>\n\n"
            "This will remove ALL your subscriptions. You can always subscribe again later.\n\n"
            "Are you sure?"
        )
        assert buttons(query.last.reply_markup) == [
            ("✅ Yes, Remove All", "unsub_all_confirm"),
            ("❌ Cancel", "myservices"),
        ]

    async def test_confirmation_russian(self, db):
        add_user(db, "ru")
        query = await press("unsub_all")
        assert query.last.text == (
            "⚠️ <b>Отписаться от всех услуг?</b>\n\n"
            "Все ваши подписки будут удалены. Вы сможете подписаться снова в любой момент.\n\n"
            "Вы уверены?"
        )
        assert buttons(query.last.reply_markup) == [
            ("✅ Да, удалить все", "unsub_all_confirm"),
            ("❌ Отмена", "myservices"),
        ]

    async def test_confirmed_russian(self, db):
        add_user(db, "ru")
        subscribe(db, 1, 10)
        subscribe(db, 2, 10)
        query = await press("unsub_all_confirm")
        assert query.answers[-1] == ("🗑 Удалено 2 подписки", True)
        assert query.last.text.startswith("📋 <b>Нет подписок</b>")

    async def test_confirmed_english(self, db):
        add_user(db, "en")
        subscribe(db, 1, 10)
        query = await press("unsub_all_confirm")
        assert query.answers[-1] == ("🗑 Removed 1 subscription(s)", True)


def preset(days: int) -> tuple[str, str]:
    today = datetime.now()
    return today.strftime("%Y-%m-%d"), (today + timedelta(days=days)).strftime(
        "%Y-%m-%d"
    )


@pytest.mark.asyncio
class TestSetDates:
    async def test_screen_english(self, db):
        add_user(db, "en")
        query = await press("setdates")
        assert query.last.text == (
            "📅 <b>Set Date Range</b>\n\n"
            f"Current range: <b>{START}</b> to <b>{END}</b>\n\n"
            "Choose a preset or use a custom range:\n\n"
            "<b>Custom Range:</b>\n"
            "<code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
            "<b>Example:</b> <code>/setdates 2025-10-01 2025-10-31</code>"
        )
        today, _ = preset(0)
        assert buttons(query.last.reply_markup) == [
            (f"📅 Next 2 days ({today} to {preset(2)[1]})", "setdates:2"),
            (f"📅 Next week ({today} to {preset(7)[1]})", "setdates:7"),
            (f"📅 Next 30 days ({today} to {preset(30)[1]})", "setdates:30"),
            (f"📅 Next 3 months ({today} to {preset(90)[1]})", "setdates:90"),
            (f"📅 Next 6 months ({today} to {preset(180)[1]})", "setdates:180"),
            ("🏠 Main Menu", "main_menu"),
        ]

    async def test_screen_russian(self, db):
        add_user(db, "ru")
        query = await press("setdates")
        assert query.last.text == (
            "📅 <b>Выбор периода дат</b>\n\n"
            f"Текущий период: <b>{START}</b> — <b>{END}</b>\n\n"
            "Выберите готовый период или укажите свой:\n\n"
            "<b>Свой период:</b>\n"
            "<code>/setdates ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>\n\n"
            "<b>Пример:</b> <code>/setdates 2025-10-01 2025-10-31</code>"
        )
        today, _ = preset(0)
        assert buttons(query.last.reply_markup) == [
            (f"📅 Ближайшие 2 дня ({today} — {preset(2)[1]})", "setdates:2"),
            (f"📅 Ближайшая неделя ({today} — {preset(7)[1]})", "setdates:7"),
            (f"📅 Ближайшие 30 дней ({today} — {preset(30)[1]})", "setdates:30"),
            (f"📅 Ближайшие 3 месяца ({today} — {preset(90)[1]})", "setdates:90"),
            (f"📅 Ближайшие 6 месяцев ({today} — {preset(180)[1]})", "setdates:180"),
            ("🏠 Главное меню", "main_menu"),
        ]

    async def test_preset_alert(self, db, check_stats, events):
        add_user(db, "en")
        query = await press("setdates:7")
        assert query.answers[-1] == ("✅ Date range set: next 7 days", True)
        assert (
            "date_range_set",
            {"user_id": USER_ID, "range_days": 7, "range_direction": "set"},
        ) in events

        add_user_lang(db, "ru")
        query = await press("setdates:2")
        assert query.answers[-1] == ("✅ Период дат задан: ближайшие 2 дня", True)
        assert query.last.text.startswith("📊 <b>Ваш статус</b>")


@pytest.mark.asyncio
class TestStatus:
    async def test_not_registered(self, db):
        query = await press("status")
        assert (
            query.last.text == "❌ You are not registered.\n\nUse /start to register."
        )
        assert buttons(query.last.reply_markup) == [("🏠 Main Menu", "main_menu")]

    async def test_not_registered_russian_cache(self, db):
        query = await press("status", SimpleNamespace(user_data={"lang": "ru"}))
        assert query.last.text == (
            "❌ Вы не зарегистрированы.\n\nЧтобы зарегистрироваться, отправьте /start."
        )
        assert buttons(query.last.reply_markup) == [("🏠 Главное меню", "main_menu")]

    async def test_english_never_checked(self, db, check_stats):
        add_user(db, "en")
        interval = get_config().check_interval
        query = await press("status")
        assert query.last.text == (
            "📊 <b>Your Status</b>\n\n"
            f"👤 User ID: <code>{USER_ID}</code>\n"
            "📋 Subscriptions: <b>0</b>\n"
            f"📅 Date Range: {START} to {END}\n"
            "🌐 Language: 🇬🇧 English\n\n"
            "🔍 Last checked: Never\n"
            "⏱ Next check in: Soon\n"
            f"⚙️ Check interval: {interval} seconds"
            "\n🎯 Appointments found: 0\n\n"
            "👥 Total Users: <b>1</b>"
        )
        assert buttons(query.last.reply_markup) == [("🏠 Main Menu", "main_menu")]

    async def test_russian_never_checked(self, db, check_stats, monkeypatch):
        add_user(db, "ru")
        monkeypatch.setattr(get_config(), "check_interval", 120)
        query = await press("status")
        assert query.last.text == (
            "📊 <b>Ваш статус</b>\n\n"
            f"👤 ID пользователя: <code>{USER_ID}</code>\n"
            "📋 Подписки: <b>0</b>\n"
            f"📅 Период дат: {START} — {END}\n"
            "🌐 Язык: 🇷🇺 Русский\n\n"
            "🔍 Последняя проверка: ещё не проводилась\n"
            "⏱ Следующая проверка: скоро\n"
            "⚙️ Интервал проверки: 120 секунд"
            "\n🎯 Найдено записей: 0\n\n"
            "👥 Всего пользователей: <b>1</b>"
        )
        assert buttons(query.last.reply_markup) == [("🏠 Главное меню", "main_menu")]

    async def test_timing_and_found_appointments(self, db, check_stats):
        add_user(db, "ru")
        subscribe(db, 1, 10)
        with Session(db) as session:
            session.add(
                AppointmentLog(
                    service_id=1,
                    office_id=10,
                    data="{}",
                    found_at=datetime.now() - timedelta(days=3, hours=1),
                )
            )
            session.commit()
        check_stats(datetime.now() - timedelta(seconds=125))

        query = await press("status")
        assert "🔍 Последняя проверка: 2 минуты назад\n" in query.last.text
        assert "\n🎯 Найдено записей: 1 (последняя: 3 дня назад)\n" in query.last.text

        add_user_lang(db, "en")
        query = await press("status")
        assert "🔍 Last checked: 2 minutes ago\n" in query.last.text
        assert "\n🎯 Appointments found: 1 (last: 3 days ago)\n" in query.last.text

    @pytest.mark.parametrize(
        ("lang", "interval", "expected"),
        [
            ("en", 120, "⚙️ Check interval: 120 seconds\n"),
            ("en", 1, "⚙️ Check interval: 1 seconds\n"),
            ("ru", 120, "⚙️ Интервал проверки: 120 секунд\n"),
            ("ru", 21, "⚙️ Интервал проверки: 21 секунда\n"),
            ("ru", 22, "⚙️ Интервал проверки: 22 секунды\n"),
        ],
    )
    async def test_check_interval_unit(
        self, db, check_stats, monkeypatch, lang, interval, expected
    ):
        add_user(db, lang)
        monkeypatch.setattr(get_config(), "check_interval", interval)
        query = await press("status")
        assert expected in query.last.text


@pytest.mark.asyncio
class TestInterruptedBooking:
    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            (
                "en",
                (
                    "❌ Your booking session was interrupted (bot restarted).\n\n"
                    "Please start a new booking from an appointment notification."
                ),
            ),
            (
                "ru",
                (
                    "❌ Процесс записи прервался (бот был перезапущен).\n\n"
                    "Пожалуйста, начните запись заново из уведомления о свободной записи."
                ),
            ),
        ],
    )
    async def test_message(self, db, lang, text):
        add_user(db, lang)
        with Session(db) as session:
            BookingSessionRepository(session).create_session(
                user_id=USER_ID,
                state="select_time",
                service_id=1,
                office_id=10,
                date="2026-11-02",
                captcha_token="token",
                expires_at=datetime.now(UTC).replace(tzinfo=None)
                + timedelta(minutes=10),
            )
        query = await press("cancel_booking")
        assert query.last.text == text


@pytest.mark.asyncio
class TestAdminStatsStayEnglish:
    async def test_stats_inline_is_english_for_russian_user(self, db):
        add_user(db, "ru")
        query = await press("show_stats")
        assert query.last.text.startswith("📈 <b>Bot Statistics</b>\n\n👥 Users: 1\n")
        assert buttons(query.last.reply_markup) == [("🏠 Main Menu", "main_menu")]


class TestCatalogTexts:
    @pytest.mark.parametrize(
        ("lang", "text"),
        [("en", "❌ Subscription failed"), ("ru", "❌ Не удалось оформить подписку")],
    )
    def test_failure_alert_text(self, lang, text):
        assert t("buttons.subscription_failed", lang) == text

    @pytest.mark.parametrize(
        ("count", "text"),
        [(1, "1 подписка"), (3, "3 подписки"), (5, "5 подписок"), (21, "21 подписка")],
    )
    def test_russian_total_plural(self, count, text):
        assert (
            t("buttons.subscriptions_total", "ru", count=count)
            == f"<b>Всего:</b> {text}"
        )

    @pytest.mark.parametrize("count", [1, 2])
    def test_english_total_unchanged(self, count):
        assert (
            t("buttons.subscriptions_total", "en", count=count)
            == f"<b>Total:</b> {count} subscription(s)"
        )

    @pytest.mark.parametrize(
        ("count", "text"),
        [
            (1, "🗑 Удалена 1 подписка"),
            (5, "🗑 Удалено 5 подписок"),
            (0, "🗑 Удалено 0 подписок"),
        ],
    )
    def test_russian_removed_plural(self, count, text):
        assert t("buttons.removed_subscriptions", "ru", count=count) == text

    @pytest.mark.parametrize(
        ("count", "text"),
        [
            (1, "ближайший 1 день"),
            (2, "ближайшие 2 дня"),
            (30, "ближайшие 30 дней"),
            (180, "ближайшие 180 дней"),
        ],
    )
    def test_russian_alert_plural(self, count, text):
        assert (
            t("buttons.date_range_set", "ru", count=count)
            == f"✅ Период дат задан: {text}"
        )

    @pytest.mark.parametrize(
        ("key", "count", "text"),
        [
            ("buttons.seconds_ago", 1, "1 секунду назад"),
            ("buttons.seconds_ago", 3, "3 секунды назад"),
            ("buttons.seconds_ago", 45, "45 секунд назад"),
            ("buttons.minutes_ago", 21, "21 минуту назад"),
            ("buttons.minutes_ago", 5, "5 минут назад"),
            ("buttons.hours_ago", 1, "1 час назад"),
            ("buttons.hours_ago", 2, "2 часа назад"),
            ("buttons.hours_ago", 11, "11 часов назад"),
            ("buttons.days_ago", 2, "2 дня назад"),
            ("buttons.days_ago", 5, "5 дней назад"),
            ("buttons.next_check_seconds", 1, "через ~1 секунду"),
            ("buttons.next_check_seconds", 30, "через ~30 секунд"),
            ("buttons.next_check_minutes", 2, "через ~2 минуты"),
            ("buttons.next_check_minutes", 1, "через ~1 минуту"),
        ],
    )
    def test_russian_time_plurals(self, key, count, text):
        assert t(key, "ru", count=count) == text

    @pytest.mark.parametrize(
        ("key", "text"),
        [
            ("buttons.seconds_ago", "{} seconds ago"),
            ("buttons.minutes_ago", "{} minutes ago"),
            ("buttons.hours_ago", "{} hours ago"),
            ("buttons.days_ago", "{} days ago"),
            ("buttons.next_check_seconds", "~{} seconds"),
            ("buttons.next_check_minutes", "~{} minutes"),
        ],
    )
    @pytest.mark.parametrize("count", [1, 7])
    def test_english_time_unchanged(self, key, text, count):
        assert t(key, "en", count=count) == text.format(count)

    @pytest.mark.parametrize(
        ("key", "en", "ru"),
        [
            ("buttons.today", "today", "сегодня"),
            ("buttons.yesterday", "yesterday", "вчера"),
            ("buttons.recently", "recently", "недавно"),
        ],
    )
    def test_relative_days(self, key, en, ru):
        assert t(key, "en") == en
        assert t(key, "ru") == ru
