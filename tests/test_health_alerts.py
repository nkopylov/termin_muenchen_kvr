# ABOUTME: Tests for the admin health alerts of the checker: one alert when a failure streak starts,
# ABOUTME: one message when checks recover, and readable reasons for city outages.

import pytest
from sqlmodel import Session

from src.config import get_config
from src.munich_api_client import ApiResponse
from src.repositories import UserRepository, WatchRepository
from src.services import appointment_checker
from src.services.appointment_checker import HealthState, check_iteration
from src.watches.when import PRESETS
from tests.conftest import NOW
from tests.fakes import FakeApplication, FakeBot, calendar

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("catalog", "today", "clock")]

ADMIN = 999000
USER = 101
SERVICE = 1063475
OFFICE = 102526


@pytest.fixture(autouse=True)
def checker_state(monkeypatch):
    monkeypatch.setattr(appointment_checker, "_catalog_refreshed_at", NOW)
    monkeypatch.setattr(appointment_checker, "_paused_swept_on", None)
    stats = {
        key: 0 if isinstance(value, int) else None
        for key, value in appointment_checker.stats.items()
    }
    monkeypatch.setattr(appointment_checker, "stats", stats)
    monkeypatch.setattr(get_config(), "admin_telegram_id", ADMIN)


@pytest.fixture
def watch(db):
    with Session(db) as session:
        UserRepository(session).create_user(USER, language="en")
        WatchRepository(session).create_or_update(
            USER, SERVICE, OFFICE, PRESETS["asap"]
        )


def admin_messages(bot) -> list[str]:
    return [c.text for c in bot.sent if c.chat_id == ADMIN]


UNAVAILABLE = ApiResponse(None, 503, ())


def available() -> ApiResponse:
    return ApiResponse(calendar(), 200, ())


async def run(app, health, times):
    for _ in range(times):
        await check_iteration(app, health)


@pytest.mark.usefixtures("watch")
async def test_alert_is_sent_once_while_the_failure_streak_continues(
    fake_api, fake_token
):
    fake_api["get"] = [UNAVAILABLE] * 9
    bot = FakeBot()

    await run(FakeApplication(bot), HealthState(), 9)

    [alert] = admin_messages(bot)
    assert "failed 5 consecutive checks" in alert


@pytest.mark.usefixtures("watch")
async def test_recovery_is_reported_once_and_a_later_streak_alerts_again(
    fake_api, fake_token
):
    fake_api["get"] = [UNAVAILABLE] * 6 + [available()] * 2 + [UNAVAILABLE] * 5
    bot = FakeBot()
    app, health = FakeApplication(bot), HealthState()

    await run(app, health, 6)
    await run(app, health, 2)
    assert len(admin_messages(bot)) == 2
    assert "recovered" in admin_messages(bot)[1]
    assert "6 failed checks" in admin_messages(bot)[1]

    await run(app, health, 5)
    assert len(admin_messages(bot)) == 3
    assert "failed 5 consecutive checks" in admin_messages(bot)[2]


@pytest.mark.usefixtures("watch")
async def test_no_recovery_message_without_an_alert(fake_api, fake_token):
    fake_api["get"] = [UNAVAILABLE] * 3 + [available()]
    bot = FakeBot()

    await run(FakeApplication(bot), HealthState(), 4)

    assert admin_messages(bot) == []


@pytest.mark.usefixtures("watch")
async def test_server_error_is_named_as_city_api_unavailable(fake_api, fake_token):
    fake_api["get"] = [UNAVAILABLE] * 5
    bot = FakeBot()

    await run(FakeApplication(bot), HealthState(), 5)

    [alert] = admin_messages(bot)
    assert f"service {SERVICE}: city API unavailable (HTTP 503)" in alert


@pytest.mark.usefixtures("watch")
async def test_missing_captcha_token_is_named(fake_api, fake_token):
    fake_token["fail"] = True
    bot = FakeBot()

    await run(FakeApplication(bot), HealthState(), 5)

    [alert] = admin_messages(bot)
    assert f"service {SERVICE}: captcha unavailable" in alert
    assert fake_api["calls"] == []
