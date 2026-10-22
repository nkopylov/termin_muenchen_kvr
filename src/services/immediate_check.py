# ABOUTME: Checks a watch right after it is created or changed and shows the result as its live alert.
# ABOUTME: The handler returns at once; the network part runs as a per-user background task.

from telegram import Update
from telegram.ext import ContextTypes

from src.watches.when import WhenSpec


async def start_watch_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    service_id: int,
    office_id: int | None,
    when: WhenSpec,
    *,
    target_message_id: int | None,
) -> None:
    raise NotImplementedError


async def start_recheck(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    watch_id: int,
    when: WhenSpec,
    *,
    target_message_id: int | None,
) -> None:
    """When WatchRepository.set_when returns another watch (an ended watch whose service
    already has an open one), the live alert of `watch_id` is closed as outdated under
    alert_lock(watch_id), or only cleared when it is the target message, and the result
    carries alert.updated_existing."""
    raise NotImplementedError
