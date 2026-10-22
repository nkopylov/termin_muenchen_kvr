# ABOUTME: Tests for database migration v2: added columns, watches built from subscriptions, idempotency.
# ABOUTME: Uses temp-file SQLite databases created with the v1 schema by hand.

import sqlite3
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from src import database
from src.database import _migrate_subscriptions_to_watches
from src.repositories import WatchRepository
from src.watches import when as when_module
from src.watches.when import WhenSpec

TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 8, 0)

V1_SCHEMA = """
CREATE TABLE users (
    user_id INTEGER NOT NULL PRIMARY KEY,
    username VARCHAR(255),
    subscribed_at DATETIME NOT NULL,
    start_date VARCHAR(10),
    end_date VARCHAR(10),
    language VARCHAR(2) NOT NULL
);
CREATE TABLE service_subscriptions (
    id INTEGER NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (user_id),
    service_id INTEGER NOT NULL,
    office_id INTEGER NOT NULL,
    subscribed_at DATETIME NOT NULL
);
CREATE TABLE appointment_logs (
    id INTEGER NOT NULL PRIMARY KEY,
    found_at DATETIME NOT NULL,
    service_id INTEGER NOT NULL,
    office_id INTEGER NOT NULL,
    data VARCHAR NOT NULL
);
CREATE TABLE booking_sessions (
    user_id INTEGER NOT NULL PRIMARY KEY,
    state VARCHAR(50) NOT NULL,
    service_id INTEGER NOT NULL,
    office_id INTEGER NOT NULL,
    date VARCHAR(10) NOT NULL,
    captcha_token VARCHAR(500) NOT NULL,
    timestamp INTEGER,
    name VARCHAR(255),
    email VARCHAR(255),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL
);
PRAGMA user_version = 1;
"""


@pytest.fixture
def v1_db(tmp_path, monkeypatch):
    path = tmp_path / "v1.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(V1_SCHEMA)
    engine = create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(when_module, "today_berlin", lambda: TODAY)
    yield path
    engine.dispose()


def add_user(path, user_id, start=None, end=None, language="en"):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO users VALUES (?, 'u', '2026-01-01 00:00:00', ?, ?, ?)",
            (user_id, start, end, language),
        )


def subscribe(path, user_id, service_id, office_id):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO service_subscriptions (user_id, service_id, office_id, subscribed_at)"
            " VALUES (?, ?, ?, '2026-01-01 00:00:00')",
            (user_id, service_id, office_id),
        )


def watches(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM watches ORDER BY id")]


def columns(path, table):
    with sqlite3.connect(path) as conn:
        return {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def user_version(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


class TestSchema:
    def test_adds_columns_and_tables(self, v1_db):
        database.init_database()

        user_cols = columns(v1_db, "users")
        for name in ("booking_name", "booking_email", "nav_message_id", "ui_version"):
            assert name in user_cols
        assert {"watch_id", "message_id"} <= set(columns(v1_db, "booking_sessions"))
        assert "alert_message_id" in columns(v1_db, "watches")
        assert "not_before" in columns(v1_db, "pending_retires")
        assert user_version(v1_db) == 2

    def test_ui_version_default_on_migrated_schema(self, v1_db):
        add_user(v1_db, 1)
        database.init_database()

        assert columns(v1_db, "users")["ui_version"][4] is not None
        with sqlite3.connect(v1_db) as conn:
            conn.execute(
                "INSERT INTO users (user_id, subscribed_at, language) "
                "VALUES (2, '2026-01-01 00:00:00', 'en')"
            )
            values = dict(conn.execute("SELECT user_id, ui_version FROM users"))
        assert values == {1: 0, 2: 0}

    def test_ui_version_default_on_fresh_schema(self, tmp_path, monkeypatch):
        path = tmp_path / "fresh.db"
        engine = create_engine(f"sqlite:///{path}")
        monkeypatch.setattr(database, "_engine", engine)
        database.init_database()

        assert columns(path, "users")["ui_version"][4] is not None
        with sqlite3.connect(path) as conn:
            conn.execute(
                "INSERT INTO users (user_id, subscribed_at, language) "
                "VALUES (2, '2026-01-01 00:00:00', 'en')"
            )
            assert conn.execute("SELECT ui_version FROM users").fetchone()[0] == 0
        assert user_version(path) == 2
        engine.dispose()

    def test_columns_added_once_when_rerun(self, v1_db):
        database.init_database()
        with sqlite3.connect(v1_db) as conn:
            conn.execute("PRAGMA user_version = 1")
        database.init_database()

        names = [
            row[1] for row in sqlite3.connect(v1_db).execute("PRAGMA table_info(users)")
        ]
        assert names.count("ui_version") == 1
        assert user_version(v1_db) == 2


class TestSubscriptionsToWatches:
    def test_future_range_becomes_between_with_clipped_end(self, v1_db):
        far_end = (TODAY + timedelta(days=400)).isoformat()
        add_user(v1_db, 1, "2026-11-01", far_end)
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        [w] = watches(v1_db)
        assert (w["user_id"], w["service_id"], w["office_id"]) == (1, 100, 10)
        assert w["when_kind"] == "between"
        assert w["date_from"] == "2026-11-01"
        assert w["date_to"] == (TODAY + timedelta(days=364)).isoformat()
        assert w["status"] == "active"
        assert w["alerted_slots"] == "[]"
        assert w["alert_shown_slots"] == "[]"
        assert w["alert_message_id"] is None

    def test_range_starting_beyond_query_horizon_is_kept(self, v1_db):
        add_user(v1_db, 1, "2028-01-01", "2028-02-01")
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        [w] = watches(v1_db)
        assert w["when_kind"] == "between"
        assert (w["date_from"], w["date_to"]) == ("2028-01-01", "2028-02-01")

    def test_past_range_is_asap(self, v1_db):
        add_user(v1_db, 1, "2026-01-01", "2026-03-01")
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        [w] = watches(v1_db)
        assert w["when_kind"] == "asap"
        assert w["date_from"] is None and w["date_to"] is None

    @pytest.mark.parametrize(
        ("start", "end"), [(None, None), ("", ""), ("2026-12-01", None)]
    )
    def test_missing_dates_are_asap(self, v1_db, start, end):
        add_user(v1_db, 1, start, end)
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        assert watches(v1_db)[0]["when_kind"] == "asap"

    def test_unpadded_dates_are_written_as_iso(self, v1_db):
        add_user(v1_db, 1, "2026-11-1", "2026-12-5")
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        [w] = watches(v1_db)
        assert (w["date_from"], w["date_to"]) == ("2026-11-01", "2026-12-05")

    def test_reversed_range_is_asap(self, v1_db):
        add_user(v1_db, 1, "2026-12-05", "2026-11-01")
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        assert watches(v1_db)[0]["when_kind"] == "asap"

    def test_running_default_signup_range_is_asap(self, v1_db):
        start = TODAY - timedelta(days=30)
        add_user(v1_db, 1, start.isoformat(), (start + timedelta(days=180)).isoformat())
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        assert watches(v1_db)[0]["when_kind"] == "asap"

    def test_several_offices_of_one_service_become_any_office(self, v1_db):
        add_user(v1_db, 1)
        subscribe(v1_db, 1, 100, 10)
        subscribe(v1_db, 1, 100, 11)
        subscribe(v1_db, 1, 200, 20)
        database.init_database()

        rows = {(w["service_id"], w["office_id"]) for w in watches(v1_db)}
        assert rows == {(100, None), (200, 20)}

    def test_more_than_five_services_are_kept(self, v1_db):
        add_user(v1_db, 1)
        for service_id in range(1, 8):
            subscribe(v1_db, 1, service_id, 10)
        database.init_database()

        assert len(watches(v1_db)) == 7

    def test_old_data_untouched(self, v1_db):
        add_user(v1_db, 1, "2026-11-01", "2026-12-01")
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        with sqlite3.connect(v1_db) as conn:
            assert conn.execute(
                "SELECT start_date, end_date FROM users"
            ).fetchone() == (
                "2026-11-01",
                "2026-12-01",
            )
            assert conn.execute(
                "SELECT COUNT(*) FROM service_subscriptions"
            ).fetchone() == (1,)

    def test_rerun_creates_no_duplicates(self, v1_db):
        add_user(v1_db, 1)
        subscribe(v1_db, 1, 100, 10)
        database.init_database()
        with database.get_engine().begin() as conn:
            assert _migrate_subscriptions_to_watches(conn, TODAY, NOW) == 0
        database.init_database()

        assert len(watches(v1_db)) == 1

    def test_watches_readable_by_repository(self, v1_db):
        add_user(v1_db, 1, "2026-11-01", "2026-12-01")
        subscribe(v1_db, 1, 100, 10)
        database.init_database()

        with Session(database.get_engine()) as session:
            [rec] = WatchRepository(session).list_active()
        assert rec.when == WhenSpec(
            "between", date_from=date(2026, 11, 1), date_to=date(2026, 12, 1)
        )
        assert rec.alerted == frozenset() and rec.live is None

    def test_fresh_database_runs_both_migrations(self, tmp_path, monkeypatch):
        engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
        monkeypatch.setattr(database, "_engine", engine)
        database.init_database()

        assert user_version(tmp_path / "f.db") == 2
        assert watches(tmp_path / "f.db") == []
        engine.dispose()
