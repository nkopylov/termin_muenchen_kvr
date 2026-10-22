"""
Pytest configuration and shared fixtures for tests
"""

from datetime import date, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from tests.fakes import FakeBot, FakeContext, Recorder

CATALOG_SERVICES = [
    {
        "id": 10339028,
        "name": "Notfall-Hilfe Aufenthaltstitel – Beschäftigte, Angehörige",
    },
    {
        "id": 10339027,
        "name": "Notfall-Hilfe Aufenthaltstitel – Studierende, Arbeitsplatzsuche nach "
        "Studium oder erstmalige Beschäftigung nach Studium",
    },
    {
        "id": 10502137,
        "name": "Abholung elektronischer Aufenthaltstitel, elektronischer Reiseausweis",
    },
    {"id": 1063475, "name": "Wohnsitzanmeldung"},
    {"id": 1063441, "name": "Personalausweis"},
    {"id": 1063453, "name": "Reisepass"},
    {"id": 1071896, "name": "Umschreibung eines ausländischen Führerscheins"},
    {"id": 1064305, "name": "Fahrzeug abmelden"},
    {"id": 1063423, "name": "Gewerbe-Anmeldung"},
    {"id": 1071907, "name": "Einbürgerung"},
    {"id": 1072043, "name": "Bewohnerparkausweis"},
    {"id": 1080479, "name": "Altersrente (Vor-Ort-Termin)"},
    {"id": 10113239, "name": "Elternberatung zur Kinderbetreuung"},
    {"id": 1063519, "name": "Fundsache abholen"},
]
BUERGERBUERO = {
    102522: "Bürgerbüro Orleansplatz",
    102523: "Bürgerbüro Leonrodstraße",
    102524: "Bürgerbüro Scheidplatz",
    102526: "Bürgerbüro Forstenrieder Allee",
    10313237: "Bürgerbüro Ruppertstraße",
    10489: "Bürgerbüro Ruppertstraße",
    54261: "Bürgerbüro Pasing",
}
SINGLE_OFFICE = {
    10339028: (10461, "Servicestelle für Zuwanderung und Einbürgerung"),
    10339027: (10187259, "Servicestelle für Zuwanderung und Einbürgerung"),
    10502137: (10456, "Dokumentenausgabe"),
    1071896: (10308174, "Führerscheinstelle"),
    1064305: (102101, "KfZ Zulassungsstelle"),
    1063423: (10546, "Gewerbeamt"),
    1071907: (10471, "Einbürgerungsbehörde"),
    1072043: (10427, "Kommunale Verkehrsüberwachung"),
    1080479: (10515, "Versicherungsamt"),
    10113239: (10300, "Elternberatung"),
    1063519: (10310, "Fundbüro"),
}
SEVEN_OFFICE_SERVICES = (1063475, 1063441, 1063453)


def catalog_payload() -> dict:
    offices = [{"id": oid, "name": name} for oid, name in BUERGERBUERO.items()]
    offices += [{"id": oid, "name": name} for oid, name in SINGLE_OFFICE.values()]
    relations = [
        {"serviceId": sid, "officeId": oid, "public": True}
        for sid in SEVEN_OFFICE_SERVICES
        for oid in BUERGERBUERO
    ]
    relations += [
        {"serviceId": sid, "officeId": oid, "public": True}
        for sid, (oid, _) in SINGLE_OFFICE.items()
    ]
    return {"services": CATALOG_SERVICES, "offices": offices, "relations": relations}


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    """Create in-memory SQLite database engine for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Keep single connection for in-memory DB
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="db_session")
def db_session_fixture(db_engine):
    """Create database session for testing"""
    with Session(db_engine) as session:
        yield session
        session.rollback()  # Rollback any uncommitted changes after test


@pytest.fixture
def db(monkeypatch, db_engine):
    """In-memory database used by code that calls src.database.get_session()"""
    from src import database

    monkeypatch.setattr(database, "_engine", db_engine)
    return db_engine


@pytest.fixture
def catalog(monkeypatch):
    """City catalog with the popular services, 1-office and 7-office services"""
    from src import services_manager

    payload = catalog_payload()
    monkeypatch.setattr(services_manager, "_full_payload_cache", payload)
    monkeypatch.setattr(services_manager, "_services_cache", payload["services"])
    return payload


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture
def context(fake_bot):
    return FakeContext(fake_bot)


TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 8, 0, 0)


@pytest.fixture
def today(monkeypatch):
    """Fixes when.today_berlin(); returns the date"""
    from src.watches import when

    monkeypatch.setattr(when, "today_berlin", lambda: TODAY)
    return TODAY


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    """Fixes when.utcnow(); move time with `clock.now += timedelta(...)`"""
    from src.watches import when

    fixed = Clock(NOW)
    monkeypatch.setattr(when, "utcnow", fixed)
    return fixed


@pytest.fixture
def fake_token(monkeypatch):
    """Replaces captcha_token.get_token/invalidate; counts tokens and invalidations"""
    from src.services import captcha_token

    state = {"issued": 0, "invalidated": 0, "fail": False}

    async def get_token(min_ttl: float = 30.0):
        if state["fail"]:
            return None
        state["issued"] += 1
        return f"token-{state['issued']}"

    def invalidate():
        state["invalidated"] += 1

    monkeypatch.setattr(captcha_token, "get_token", get_token)
    monkeypatch.setattr(captcha_token, "invalidate", invalidate)
    return state


class FakeAvailability:
    """Scripted replacement for availability.fetch_calendar / fetch_day_times"""

    def __init__(self):
        self.calendar_calls: list[tuple] = []
        self.day_calls: list[tuple] = []
        self.calendar_results: list = []
        self.day_results: list = []
        self.gate = None

    async def fetch_calendar(self, service_id, office_ids, start, end, slots_day=None):
        self.calendar_calls.append(
            (service_id, list(office_ids), start, end, slots_day)
        )
        if self.gate is not None:
            await self.gate.wait()
        reply = self.calendar_results.pop(0)
        return reply(service_id, office_ids) if callable(reply) else reply

    async def fetch_day_times(self, service_id, office_ids, day):
        self.day_calls.append((service_id, list(office_ids), day))
        reply = self.day_results.pop(0)
        return reply(service_id, office_ids, day) if callable(reply) else reply


@pytest.fixture
def fake_availability(monkeypatch):
    from src.watches import availability

    fake = FakeAvailability()
    monkeypatch.setattr(availability, "fetch_calendar", fake.fetch_calendar)
    monkeypatch.setattr(availability, "fetch_day_times", fake.fetch_day_times)
    return fake


@pytest.fixture
def fake_api(monkeypatch):
    """Replaces MunichAPIClient.get_result/post_result with scripted ApiResponses"""
    from src.munich_api_client import MunichAPIClient

    state = {"get": [], "post": [], "calls": []}

    def get_result(self, endpoint, params=None):
        state["calls"].append(("GET", endpoint, params))
        return state["get"].pop(0)

    def post_result(self, endpoint, data):
        state["calls"].append(("POST", endpoint, data))
        return state["post"].pop(0)

    monkeypatch.setattr(MunichAPIClient, "get_result", get_result)
    monkeypatch.setattr(MunichAPIClient, "post_result", post_result)
    return state


@pytest.fixture
def events(monkeypatch):
    """track_event recorder; call events.patch(module) for each module under test"""
    recorder = Recorder()

    def patch(module):
        monkeypatch.setattr(module, "track_event", recorder)

    recorder.patch = patch
    return recorder
