# ABOUTME: Tests for the extra checks right after each quarter-hour mark, when the city releases
# ABOUTME: Notfall (emergency residence permit) slots that are gone within about two minutes.

import logging
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from src.repositories import UserRepository, WatchRepository
from src.services import appointment_checker
from src.services.appointment_checker import (
    BURST_SERVICE_IDS,
    HealthState,
    check_iteration,
    next_burst_at,
    next_wake,
    run_check_cycle,
)
from src.watches.availability import CallResult
from src.watches.when import PRESETS
from tests.conftest import NOW, TODAY
from tests.fakes import FakeApplication, FakeBot, calendar

NOTFALL_WORK = 10339028
NOTFALL_STUDY = 10339027
ANMELDUNG = 1063475


def at(hour: int, minute: int, second: int = 0, day: int = 23) -> datetime:
    return datetime(2026, 10, day, hour, minute, second)


class TestNextBurstAt:
    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (at(5, 29, 36), at(5, 30, 5)),
            (at(5, 30, 0), at(5, 30, 5)),
            (at(5, 30, 5), at(5, 30, 20)),
            (at(5, 30, 21), at(5, 30, 40)),
            (at(5, 30, 40), at(5, 31, 10)),
            (at(5, 31, 10), at(5, 45, 5)),
            (at(5, 59, 59), at(6, 0, 5)),
            (at(23, 59, 50), at(0, 0, 5, day=24)),
        ],
    )
    def test_next_moment_after_a_quarter_hour_mark(self, now, expected):
        assert next_burst_at(now) == expected

    def test_is_strictly_later(self):
        now = at(7, 15, 5)
        assert next_burst_at(now) > now


class TestNextWake:
    def test_regular_cycle_first_when_it_is_due_before_the_burst(self):
        now = at(5, 20, 0)
        regular_due = now + timedelta(seconds=120)
        assert next_wake(now, regular_due) == (regular_due, False)

    def test_burst_first_when_it_comes_before_the_regular_cycle(self):
        now = at(5, 29, 36)
        regular_due = at(5, 31, 36)
        assert next_wake(now, regular_due) == (at(5, 30, 5), True)

    def test_regular_cycle_wins_a_tie(self):
        now = at(5, 29, 0)
        assert next_wake(now, at(5, 30, 5)) == (at(5, 30, 5), False)


def test_burst_services_are_the_notfall_residence_permit_services():
    assert BURST_SERVICE_IDS == frozenset({NOTFALL_WORK, NOTFALL_STUDY})


def add_watch(db, user_id, service_id, office_id=None):
    with Session(db) as session:
        UserRepository(session).create_user(user_id, language="en")
        rec, _ = WatchRepository(session).create_or_update(
            user_id, service_id, office_id, PRESETS["asap"]
        )
        return rec.id


@pytest.mark.asyncio
@pytest.mark.usefixtures("catalog", "today", "clock")
async def test_burst_cycle_queries_only_the_given_services(
    db, fake_availability, monkeypatch
):
    monkeypatch.setattr(appointment_checker, "_catalog_refreshed_at", NOW)
    add_watch(db, 101, NOTFALL_WORK)
    add_watch(db, 202, ANMELDUNG)
    fake_availability.calendar_results = [
        lambda _service, _offices: CallResult(True, calendar(), None)
    ]

    await run_check_cycle(FakeBot(), TODAY, NOW, services=BURST_SERVICE_IDS)

    assert [call[0] for call in fake_availability.calendar_calls] == [NOTFALL_WORK]


@pytest.mark.asyncio
@pytest.mark.usefixtures("catalog", "today", "clock")
async def test_burst_without_notfall_watches_sends_no_analytics_event(
    db, fake_availability, events, monkeypatch
):
    monkeypatch.setattr(appointment_checker, "_catalog_refreshed_at", NOW)
    events.patch(appointment_checker)
    add_watch(db, 202, ANMELDUNG)

    await check_iteration(
        FakeApplication(FakeBot()), HealthState(), services=BURST_SERVICE_IDS
    )

    assert fake_availability.calendar_calls == []
    assert [name for name, _ in events.calls] == []


def test_http_request_logs_do_not_include_the_bot_token():
    import telegram_bot  # noqa: F401

    # Set on the logger itself, so the bot's INFO root level does not reach request lines
    assert logging.getLogger("httpx").level == logging.WARNING
