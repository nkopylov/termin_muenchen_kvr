# ABOUTME: Tests for the admin /stats command: checker counters and watch counts from the DB.
# ABOUTME: Real in-memory DB and Telegram Update objects bound to a recording FakeBot.

from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from src.commands.stats import stats_command
from src.config import get_config
from src.repositories import UserRepository, WatchRepository
from src.services import appointment_checker
from src.watches.when import PRESETS
from tests.fakes import FakeBot, FakeContext, make_text_update

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("catalog", "clock")]

ADMIN = 7000


@pytest.fixture
def admin(monkeypatch, db):
    monkeypatch.setattr(get_config(), "admin_telegram_id", ADMIN)
    with Session(db) as session:
        UserRepository(session).create_user(ADMIN, language="en")


@pytest.fixture
def stats(monkeypatch):
    values = {
        "total_checks": 40,
        "successful_checks": 34,
        "failed_checks": 6,
        "appointments_found_count": 3,
        "bookings_started": 2,
        "bookings_completed": 1,
        "last_check_time": datetime(2026, 10, 22, 9, 30, 5),
        "last_success_time": None,
        "bot_start_time": datetime.now() - timedelta(hours=3, minutes=45, seconds=10),
    }
    monkeypatch.setattr(appointment_checker, "stats", values)
    return values


def add_watches(db):
    with Session(db) as session:
        users = UserRepository(session)
        watches = WatchRepository(session)
        for user_id in (1, 2, 3):
            users.create_user(user_id, language="en")
        watches.create_or_update(1, 1063475, None, PRESETS["asap"])
        paused, _ = watches.create_or_update(1, 1063441, None, PRESETS["2w"])
        watches.set_status(paused.id, "paused", pause_reason="user")
        watches.create_or_update(2, 1063475, 10489, PRESETS["1m"])
        ended, _ = watches.create_or_update(3, 1063453, None, PRESETS["asap"])
        watches.set_status(ended.id, "ended", end_reason="booked")


async def run_stats(user_id=ADMIN):
    bot = FakeBot()
    await stats_command(make_text_update("/stats", user_id, bot=bot), FakeContext(bot))
    [sent] = bot.sent
    return sent


class TestStatsCommand:
    async def test_admin_sees_watch_counts_and_checker_counters(self, db, admin, stats):
        add_watches(db)

        sent = await run_stats()

        assert sent.parse_mode == "HTML"
        assert sent.text == (
            "📈 <b>Bot Statistics</b>\n\n"
            "⏱ Uptime: 3h 45m\n"
            "👥 Users: 4\n"
            "👀 Watches: 2 active, 1 paused, 1 ended\n"
            "🙋 Users with open watches: 2\n\n"
            "🔍 Total checks: 40\n"
            "✅ Successful: 34\n"
            "❌ Failed: 6\n"
            "📊 Success rate: 85.0%\n\n"
            "🎯 Appointments found: 3\n"
            "🚀 Bookings started: 2\n"
            "✅ Bookings completed: 1\n"
            "\n⏰ Last check: 09:30:05"
        )
        assert sent.reply_markup is None

    async def test_no_checks_yet(self, db, admin, stats):
        stats.update(
            total_checks=0,
            successful_checks=0,
            failed_checks=0,
            last_check_time=None,
            bot_start_time=None,
        )

        text = (await run_stats()).text

        assert "⏱ Uptime: N/A\n" in text
        assert "👀 Watches: 0 active, 0 paused, 0 ended\n" in text
        assert "📊 Success rate: 0.0%\n" in text
        assert "Last check" not in text
