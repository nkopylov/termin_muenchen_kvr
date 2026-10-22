# ABOUTME: Applies the checker's alert decisions to Telegram and the database (push, edit, retire).
# ABOUTME: Also ends watches whose deadline passed or whose office disappeared, and expired bookings.

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from src.watches.alert_decision import AlertAction
from src.watches.slots import WatchSnapshot


async def apply_alert(
    bot,
    watch_id: int,
    snapshot: WatchSnapshot,
    now: datetime,
    booking_active: Callable[[int], bool],
) -> AlertAction:
    raise NotImplementedError


async def end_watch_by_checker(
    bot,
    watch_id: int,
    reason: Literal["deadline", "gone"],
    now: datetime,
    booking_active: Callable[[int], bool],
) -> bool:
    raise NotImplementedError


async def cleanup_expired_bookings(bot) -> int:
    raise NotImplementedError
